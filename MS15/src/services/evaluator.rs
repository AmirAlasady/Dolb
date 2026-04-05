use std::sync::Arc;
use std::collections::HashMap;
use anyhow::{Result, Context};
use uuid::Uuid;

// Fix: Import RuleStatus and RunStatus explicitly
use crate::domain::enums::{RuleStatus, RunStatus};
use crate::domain::models::{InferenceRequestMessage, EvalCheckMessage};
use crate::domain::logic::{check_rule_readiness, render_prompt};
use crate::interfaces::storage_trait::StorageFacade;
use crate::interfaces::messaging_trait::MessagingFacade;

pub struct EvaluatorService<S, M> {
    storage: Arc<S>,
    messaging: Arc<M>,
}

impl<S, M> Clone for EvaluatorService<S, M> {
    fn clone(&self) -> Self {
        Self {
            storage: self.storage.clone(),
            messaging: self.messaging.clone(),
        }
    }
}

impl<S: StorageFacade, M: MessagingFacade> EvaluatorService<S, M> {
    pub fn new(storage: Arc<S>, messaging: Arc<M>) -> Self {
        Self { storage, messaging }
    }

    pub async fn process_check(&self, msg: EvalCheckMessage) -> Result<()> {
        let run_id = &msg.run_id;
        let rule_id = &msg.rule_id;

        // Check if run is canceled
        if let Ok(RunStatus::Canceled) = self.storage.get_run_status(run_id).await {
            println!("🛑 Run {} is CANCELED. Skipping evaluation of rule {}.", run_id, rule_id);
            return Ok(());
        }

        let status = self.storage.get_rule_status(run_id, rule_id).await?;
        if matches!(status, RuleStatus::Dispatched | RuleStatus::Completed) {
            println!("  ⏭️  Rule {} is already {:?}. Skipping eval check.", rule_id, status);
            return Ok(());
        }

        let rule = match self.storage.get_rule_blueprint(run_id, rule_id).await {
            Ok(r) => r,
            Err(e) => {
                println!("  ❌ Rule {} blueprint not found! Error: {:?}", rule_id, e);
                return Err(e.context("Rule blueprint not found"));
            }
        };

        // Load snapshot early — needed for both anchor gating and ms4_node_id lookup.
        let snapshot = self.storage.get_full_snapshot(run_id).await?;

        let mut available_inputs = Vec::new();
        let mut input_values = HashMap::new(); 

        for pid in &rule.input_projection_ids {
            if self.storage.has_input_data(run_id, pid).await? {
                available_inputs.push(pid.clone());
            }
        }

        if !check_rule_readiness(&rule, &available_inputs) {
            println!("  ⏳ Rule {} is not ready yet. Waiting for: {:?}", rule_id, rule.input_projection_ids);
            return Ok(()); 
        }

        // --- ANCHOR GATE ---
        // Feedback-family rules (inputs rooted in FBI channels) may NOT fire until the
        // node has been anchored — i.e., at least one forward-family rule has successfully
        // committed on this node in this run.
        //
        // Note: we DON'T discard the stored FBI data. We just delay evaluation.
        if !rule.is_forward_family(&snapshot) {
            let anchored = self.storage.is_node_anchored(run_id, &rule.owner_node_id).await?;
            if !anchored {
                println!(
                    "  ⚓ Rule {} is feedback-family but node {} is NOT anchored yet — holding fire.",
                    &rule_id[..8.min(rule_id.len())],
                    &rule.owner_node_id[..8.min(rule.owner_node_id.len())]
                );
                return Ok(());
            }
            println!(
                "  ✅ Node {} is anchored — feedback-family rule {} may proceed.",
                &rule.owner_node_id[..8.min(rule.owner_node_id.len())],
                &rule_id[..8.min(rule_id.len())]
            );
        }

        if !self.storage.lock_rule(run_id, rule_id).await? {
            // lock_rule itself prints "already locked, skipping"
            return Ok(());
        }
        
        let current_status = self.storage.get_rule_status(run_id, rule_id).await?;
        if matches!(current_status, RuleStatus::Dispatched | RuleStatus::Completed) {
            return Ok(());
        }

        for pid in &rule.input_projection_ids {
            if available_inputs.contains(pid) {
                let packets = self.storage.get_input_data(run_id, pid).await?;
                if let Some(packet) = packets.first() {
                    let val_str = packet.payload.to_string().trim_matches('"').to_string();
                    input_values.insert(pid.clone(), val_str);
                }
            }
        }

        let prompt_text = render_prompt(&rule.prompt_template, &rule.placeholder_map, &input_values)
            .context("Failed to render prompt template")?;

        // ms4_node_id comes from the snapshot loaded above
        let ms4_node_id = snapshot.nodes.get(&rule.owner_node_id)
            .and_then(|node| node.ms4_node_id.clone());
        
        if ms4_node_id.is_none() {
            eprintln!("⚠️  No ms4_node_id found for node {} — MS5 may fail to look up config", rule.owner_node_id);
        }

        // Look up the user_id stored when the run was created
        let user_id = self.storage.get_run_user_id(run_id).await
            .unwrap_or_else(|_| "unknown".to_string());

        let attempt_id = Uuid::new_v4().to_string();
        let request_msg = InferenceRequestMessage {
            run_id: run_id.clone(),
            rule_id: rule_id.clone(),
            node_id: rule.owner_node_id.clone(),
            ms4_node_id,
            attempt_id: attempt_id.clone(),
            prompt_text,
            metadata: HashMap::from([
                ("source".to_string(), serde_json::json!("graph_execution")),
                ("is_terminal".to_string(), serde_json::json!(rule.is_terminal)),
                ("user_id".to_string(), serde_json::json!(user_id)),
            ]),
        };

        self.messaging.publish_inference_request(request_msg).await?;
        self.storage.set_rule_status(run_id, rule_id, RuleStatus::Dispatched).await?;
        println!("🚀 Rule {} dispatched (attempt: {}, user: {})", rule_id, attempt_id, user_id);
        Ok(())
    }
}