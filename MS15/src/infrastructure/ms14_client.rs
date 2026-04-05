use reqwest::Client;
use anyhow::{Result, Context};
use serde::Deserialize;
use std::collections::HashMap;
use crate::domain::models::{
    GraphSnapshot, NodeBlueprint, FfiBlueprint, FfoBlueprint, FbiBlueprint,
    ProjectionBlueprint, RuleBlueprint,
};
use crate::domain::enums::FiringMode;

// =========================================================================
// MS14 Response DTOs — match the JSON that read_service.py actually returns
// =========================================================================

#[derive(Debug, Deserialize)]
struct Ms14Graph {
    id: String,
    project_id: String,
}

#[derive(Debug, Deserialize)]
struct Ms14Node {
    id: String,
    name: String,
    is_start: bool,
    ms4_node_id: Option<String>,
}

#[derive(Debug, Deserialize)]
struct Ms14Ffi {
    id: String,
    owner: String,   // owner_node_id
    source: String,  // source_node_id
}

#[derive(Debug, Deserialize)]
struct Ms14Ffo {
    id: String,
    owner: String,   // owner_node_id
    dest: String,    // dest_node_id
}

/// Feedback Input Buffer (FBI) — receives data routed back via FBO→FBI
#[derive(Debug, Deserialize)]
struct Ms14Fbi {
    id: String,
    owner: String,   // owner_node_id (the home-run / destination node)
    source: String,  // source_node_id (the controller node)
}

/// Feedback Output Buffer (FBO) — controller rule writes results here
#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct Ms14Fbo {
    id: String,
    owner: String,   // owner_node_id (the controller node) — kept for schema clarity
    dest: String,    // dest_node_id (the home-run / destination node)
}

#[derive(Debug, Deserialize)]
struct Ms14Projection {
    id: String,
    owner_node: String,
    ffi: Option<String>,              // source_ffi_id (forward-channel input)
    fbi: Option<String>,              // source_fbi_id (feedback-channel input)
    created_by_rule: Option<String>,  // produced_by_rule_id
    #[serde(default, alias = "children")]
    children_ids: Vec<String>,
    is_selectable: bool,
}

#[derive(Debug, Deserialize)]
struct Ms14Rule {
    id: String,
    owner_node: String,  // owner_node_id
    name: String,
    firing_mode: String, // "SINGLE", "AND", "OR"
    is_terminal: bool,
    outputs: Vec<String>,                // forward FFO ids (may be empty for controller rules)
    #[serde(default)]
    fbo_outputs: Vec<String>,           // feedback FBO ids (controller rules only)
    #[serde(default)]
    max_iterations: Option<u32>,        // loop termination bound (None = infinite)
}

#[derive(Debug, Deserialize)]
struct Ms14RuleInput {
    rule: String,
    projection: String,
    position: i32,
}

#[derive(Debug, Deserialize)]
struct Ms14PromptTemplate {
    rule: String,
    template_text: String,
    #[serde(default)]
    placeholder_map: HashMap<String, String>,
}

/// Full response shape from GET /ms14/api/v1/graph-snapshots/{id}/
#[derive(Debug, Deserialize)]
struct Ms14SnapshotResponse {
    graph: Ms14Graph,
    nodes: Vec<Ms14Node>,
    ffis: Vec<Ms14Ffi>,
    ffos: Vec<Ms14Ffo>,
    #[serde(default)]
    fbis: Vec<Ms14Fbi>,
    #[serde(default)]
    fbos: Vec<Ms14Fbo>,
    projections: Vec<Ms14Projection>,
    rules: Vec<Ms14Rule>,
    rule_inputs: Vec<Ms14RuleInput>,
    prompt_templates: Vec<Ms14PromptTemplate>,
}

// =========================================================================
// Converter: Ms14SnapshotResponse → GraphSnapshot (runtime model)
// =========================================================================

fn convert_snapshot(raw: Ms14SnapshotResponse) -> GraphSnapshot {
    // Index nodes by id
    let nodes: HashMap<_, _> = raw.nodes.into_iter().map(|n| {
        let id = n.id.clone();
        (id.clone(), NodeBlueprint {
            id,
            name: n.name,
            is_start: n.is_start,
            ms4_node_id: n.ms4_node_id,
        })
    }).collect();

    // Start node ids
    let start_node_ids: Vec<String> = nodes.values()
        .filter(|n| n.is_start)
        .map(|n| n.id.clone())
        .collect();

    // Index FFIs (forward input buffers)
    let ffis: HashMap<_, _> = raw.ffis.into_iter().map(|b| {
        let id = b.id.clone();
        (id.clone(), FfiBlueprint {
            id,
            owner_node_id: b.owner,
            source_node_id: b.source,
        })
    }).collect();

    // Index FFOs (forward output buffers)
    let ffos: HashMap<_, _> = raw.ffos.into_iter().map(|b| {
        let id = b.id.clone();
        (id.clone(), FfoBlueprint {
            id,
            owner_node_id: b.owner,
            dest_node_id: b.dest,
        })
    }).collect();

    // Index FBIs (feedback input buffers)
    // We keep both the blueprint map for snapshot AND Ms14Fbi map for local routing logic below
    let mut fbis: HashMap<String, FbiBlueprint> = HashMap::new();
    let mut fbis_by_id: HashMap<String, Ms14Fbi> = HashMap::new();
    for b in raw.fbis {
        fbis.insert(b.id.clone(), FbiBlueprint {
            id: b.id.clone(),
            owner_node_id: b.owner.clone(),
            source_node_id: b.source.clone(),
        });
        fbis_by_id.insert(b.id.clone(), b);
    }

    // Index FBOs (feedback output buffers)
    let fbos_by_id: HashMap<String, Ms14Fbo> = raw.fbos.into_iter().map(|b| (b.id.clone(), b)).collect();

    // Index Projections — include source_fbi_id for feedback-context projections
    let projections: HashMap<_, _> = raw.projections.into_iter().map(|p| {
        let id = p.id.clone();
        (id.clone(), ProjectionBlueprint {
            id,
            owner_node_id: p.owner_node,
            source_ffi_id: p.ffi,
            source_fbi_id: p.fbi,
            produced_by_rule_id: p.created_by_rule,
            children_ids: p.children_ids,
            is_selectable: p.is_selectable,
        })
    }).collect();

    // Build rule_inputs index: rule_id → ordered Vec<projection_id>
    let mut rule_inputs_map: HashMap<String, Vec<(i32, String)>> = HashMap::new();
    for ri in raw.rule_inputs {
        rule_inputs_map.entry(ri.rule).or_default().push((ri.position, ri.projection));
    }

    // Build prompt_template index: rule_id → template
    let mut prompt_map: HashMap<String, Ms14PromptTemplate> = HashMap::new();
    for tpl in raw.prompt_templates {
        prompt_map.insert(tpl.rule.clone(), tpl);
    }

    // Build rules + routing table
    let mut rules: HashMap<String, RuleBlueprint> = HashMap::new();
    let mut routes: HashMap<String, Vec<String>> = HashMap::new();

    for r in raw.rules {
        let rule_id = r.id.clone();

        // Ordered input projection ids (sort by position)
        let mut inputs = rule_inputs_map.remove(&rule_id).unwrap_or_default();
        inputs.sort_by_key(|(pos, _)| *pos);
        let input_projection_ids: Vec<String> = inputs.into_iter().map(|(_, pid)| pid).collect();

        // Prompt template
        let (prompt_template, placeholder_map) = prompt_map
            .remove(&rule_id)
            .map(|t| (t.template_text, t.placeholder_map))
            .unwrap_or_else(|| ("".to_string(), HashMap::new()));

        // Firing mode
        let firing_mode = match r.firing_mode.as_str() {
            "AND"    => FiringMode::And,
            "OR"     => FiringMode::Or,
            _        => FiringMode::Single, // "SINGLE" and fallback
        };

        let mut downstream_projections: Vec<String> = Vec::new();

        // === FORWARD ROUTING (FFO → FFI → Projections) ===
        // A projection P is downstream of rule R via forward channel if:
        //   1. P.source_ffi_id is set AND the FFI is sourced from one of R's FFO.dest_nodes
        //   2. P.produced_by_rule_id == R.id  ← CRITICAL: only the projection THIS rule created,
        //      not ALL projections on the dest node reachable via the same FFI channel.
        //      (e.g. both B[A[I]] and B[A[~B[A[I]]]] share the same FFI(B←A), but only
        //       B[A[I]] was created by r1; B[A[~B[A[I]]]] was created by r3.)
        let ffo_downstream: Vec<String> = projections.values()
            .filter(|p| {
                // Must be created by THIS rule
                p.produced_by_rule_id.as_deref() == Some(&rule_id) &&
                // Must route through a forward channel matching one of our FFO outputs
                p.source_ffi_id.as_ref().map_or(false, |ffi_id| {
                    ffis.get(ffi_id).map_or(false, |ffi| {
                        r.outputs.iter().any(|ffo_id| {
                            ffos.get(ffo_id).map_or(false, |ffo| ffo.dest_node_id == ffi.owner_node_id)
                        })
                    })
                })
            })
            .map(|p| p.id.clone())
            .collect();

        downstream_projections.extend(ffo_downstream);

        // === FEEDBACK ROUTING (FBO → FBI → Projections) ===
        // A projection P is downstream of controller rule R via feedback channel if:
        //   1. P.source_fbi_id is set AND that FBI's source_node is R's owner_node AND
        //      an FBO.dest matches that FBI.owner
        //   2. P.produced_by_rule_id == R.id  ← same precision rule as above:
        //      only the FBI-origin projection THIS controller rule created.
        if !r.fbo_outputs.is_empty() {
            let fbo_downstream: Vec<String> = projections.values()
                .filter(|p| {
                    // Must be created by THIS rule
                    p.produced_by_rule_id.as_deref() == Some(&rule_id) &&
                    // Must route through a feedback channel matching one of our FBO outputs
                    p.source_fbi_id.as_ref().map_or(false, |fbi_id| {
                        fbis_by_id.get(fbi_id).map_or(false, |fbi| {
                            fbi.source == r.owner_node &&
                            r.fbo_outputs.iter().any(|fbo_id| {
                                fbos_by_id.get(fbo_id).map_or(false, |fbo| {
                                    fbo.dest == fbi.owner
                                })
                            })
                        })
                    })
                })
                .map(|p| p.id.clone())
                .collect();

            println!(
                "  🔁 Controller rule {} has {} FBO outputs → {} feedback projections wired",
                &rule_id[..8.min(rule_id.len())],
                r.fbo_outputs.len(),
                fbo_downstream.len()
            );

            downstream_projections.extend(fbo_downstream);
        }

        if !downstream_projections.is_empty() {
            routes.insert(rule_id.clone(), downstream_projections);
        }

        rules.insert(rule_id.clone(), RuleBlueprint {
            id: rule_id,
            owner_node_id: r.owner_node,
            name: r.name,
            firing_mode,
            is_terminal: r.is_terminal,
            input_projection_ids,
            output_ffo_ids: r.outputs,
            output_fbo_ids: r.fbo_outputs, // controller/looping rules — feeds back via FBI
            prompt_template,
            placeholder_map,
            max_iterations: r.max_iterations, // loop termination bound (None = infinite)
        });
    }

    GraphSnapshot {
        graph_id: raw.graph.id,
        project_id: raw.graph.project_id,
        nodes,
        ffis,
        ffos,
        fbis,
        projections,
        rules,
        start_node_ids,
        routes,
    }
}

// =========================================================================
// Client
// =========================================================================

#[derive(Clone)]
pub struct Ms14Client {
    client: Client,
    base_url: String,
}

impl Ms14Client {
    pub fn new(base_url: String) -> Self {
        Self {
            client: Client::new(),
            base_url,
        }
    }

    pub async fn fetch_graph_snapshot(&self, graph_id: &str, jwt_token: &str) -> Result<GraphSnapshot> {
        let url = format!("{}/ms14/api/v1/graph-snapshots/{}/", self.base_url, graph_id);

        let response = self.client.get(&url)
            .header("Authorization", format!("Bearer {}", jwt_token))
            .send()
            .await
            .context("Failed to send request to MS14")?;

        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("MS14 returned error {}: {}", status, text));
        }

        // Deserialize into the MS14-shaped DTO, then convert to our runtime model
        let raw: Ms14SnapshotResponse = response.json().await
            .context("Failed to deserialize MS14 snapshot response")?;

        Ok(convert_snapshot(raw))
    }
}