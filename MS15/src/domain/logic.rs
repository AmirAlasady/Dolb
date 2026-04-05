use crate::domain::enums::{FiringMode, RuleStatus};
use crate::domain::errors::DomainError;
use crate::domain::models::{DataPacket, GraphSnapshot, ProjectionId, RuleBlueprint, RuleId};
use serde_json::Value;
use std::collections::HashMap;

// =========================================================================
// 1. READINESS LOGIC
// =========================================================================

/// Pure function to determine if a rule is ready to fire.
pub fn check_rule_readiness(rule: &RuleBlueprint, available_inputs: &[String]) -> bool {
    if rule.input_projection_ids.is_empty() {
        return false;
    }

    match rule.firing_mode {
        FiringMode::Single => {
            if let Some(required_pid) = rule.input_projection_ids.first() {
                available_inputs.contains(required_pid)
            } else {
                false
            }
        }
        FiringMode::And => rule
            .input_projection_ids
            .iter()
            .all(|req_pid| available_inputs.contains(req_pid)),
        FiringMode::Or => rule
            .input_projection_ids
            .iter()
            .any(|req_pid| available_inputs.contains(req_pid)),
    }
}

// =========================================================================
// 2. CONTEXT ASSEMBLER (The Prompt Renderer)
// =========================================================================

/// Merges the Template, the Placeholder Map, and the Actual Data Values.
///
/// # Arguments
/// * `template` - The raw string: "Summarize this: {in1} and this: {in2}"
/// * `placeholders` - Map of "{in1}" -> "Projection_UUID_A"
/// * `values` - Map of "Projection_UUID_A" -> "The actual text content"
pub fn render_prompt(
    template: &str,
    placeholders: &HashMap<String, String>,
    values: &HashMap<String, String>,
) -> Result<String, DomainError> {
    let mut rendered = template.to_string();

    for (placeholder_key, projection_id) in placeholders {
        // 1. Check if we have a value for this projection
        let val = values.get(projection_id).ok_or_else(|| {
            DomainError::DataCorruption(format!(
                "Missing value for projection '{}' required by placeholder '{}'",
                projection_id, placeholder_key
            ))
        })?;

        // 2. Replace "{in1}" with the actual value
        // Note: simplified replacement. In production, use a regex or template engine if needed.
        let token = format!("{{{}}}", placeholder_key); // e.g. "{in1}"
        rendered = rendered.replace(&token, val);
    }

    Ok(rendered)
}

// =========================================================================
// 3. COMPLETION LOGIC (The Exit Condition)
// =========================================================================

/// Determines if the entire Graph Run is finished based on MVP Policy.
///
/// **MVP Policy:** A run is complete when ALL rules marked as `is_terminal`
/// have reached the `Completed` state.
pub fn check_run_completion(
    snapshot: &GraphSnapshot,
    rule_states: &HashMap<String, RuleStatus>,
) -> bool {
    let terminal_rules: Vec<&RuleBlueprint> =
        snapshot.rules.values().filter(|r| r.is_terminal).collect();

    // If a graph has no terminal rules (invalid?), it technically never completes in this logic.
    if terminal_rules.is_empty() {
        return false;
    }

    // Check if ALL terminal rules are Completed
    terminal_rules.iter().all(|rule| {
        match rule_states.get(&rule.id) {
            Some(RuleStatus::Completed) => true,
            _ => false, // Idle, Ready, Dispatched, or Failed means not done.
        }
    })
}

// --- EXTENDED UNIT TESTS ---
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_prompt_success() {
        let template = "User said: {in1}. Context: {in2}";

        let mut placeholders = HashMap::new();
        placeholders.insert("in1".to_string(), "proj_A".to_string());
        placeholders.insert("in2".to_string(), "proj_B".to_string());

        let mut values = HashMap::new();
        values.insert("proj_A".to_string(), "Hello".to_string());
        values.insert("proj_B".to_string(), "World".to_string());

        let result = render_prompt(template, &placeholders, &values).unwrap();
        assert_eq!(result, "User said: Hello. Context: World");
    }

    #[test]
    fn test_render_prompt_missing_value() {
        let template = "{in1}";
        let mut placeholders = HashMap::new();
        placeholders.insert("in1".to_string(), "proj_A".to_string());
        let values = HashMap::new(); // Empty!

        let result = render_prompt(template, &placeholders, &values);
        assert!(result.is_err()); // Should fail safely
    }

    #[test]
    fn test_completion_logic() {
        // Setup a fake snapshot with 1 terminal rule
        let mut rules = HashMap::new();
        let term_rule = RuleBlueprint {
            id: "R_TERM".to_string(),
            owner_node_id: "N1".to_string(),
            name: "Terminal".to_string(),
            firing_mode: FiringMode::Single,
            is_terminal: true, // <--- Key flag
            input_projection_ids: vec![],
            prompt_template: "".to_string(),
            placeholder_map: HashMap::new(),
            output_ffo_ids: vec![],
        };
        rules.insert("R_TERM".to_string(), term_rule);

        let snapshot = GraphSnapshot {
            graph_id: "G1".to_string(),
            project_id: "P1".to_string(),
            rules,
            routes: HashMap::new(),
            start_node_ids: vec![],
            nodes: HashMap::new(),
            ffis: HashMap::new(),
            ffos: HashMap::new(),
            projections: HashMap::new(),
        };

        // Case 1: Rule is Idle -> Not Complete
        let mut states = HashMap::new();
        states.insert("R_TERM".to_string(), RuleStatus::Idle);
        assert!(!check_run_completion(&snapshot, &states));

        // Case 2: Rule is Completed -> Complete!
        states.insert("R_TERM".to_string(), RuleStatus::Completed);
        assert!(check_run_completion(&snapshot, &states));
    }
}

// =========================================================================
// 4. PROPAGATION LOGIC (The Router)
// =========================================================================

/// Determines where the result of a Rule should be stored.
/// Uses the O(1) route table from the Snapshot.
///
/// # Returns
/// A list of Target Projection IDs (Inboxes) that need to receive this data.
pub fn get_downstream_projections(
    snapshot: &GraphSnapshot,
    finished_rule_id: &str,
) -> Vec<ProjectionId> {
    match snapshot.routes.get(finished_rule_id) {
        Some(targets) => targets.clone(),
        None => Vec::new(), // Terminal rule or dead end
    }
}

/// Creates the standardized data packet to be written into the buffers.
/// This ensures every packet has the correct metadata (lineage, timestamps).
pub fn create_result_packet(
    payload: Value,
    source_rule_id: &str,
    source_node_id: &str,
) -> DataPacket {
    // In a real system, you might use SystemTime here,
    // but pure logic usually accepts time as an arg to remain deterministic.
    // For simplicity here, we assume the service creates the timestamp,
    // or we use a crate like `chrono` if we allow side-effects in logic (usually discouraged).
    // Let's assume the timestamp is passed in or handled by the packet constructor in the service.

    // NOTE: For this pure function, we simply construct the struct.
    DataPacket {
        payload,
        source_rule_id: Some(source_rule_id.to_string()),
        source_node_id: Some(source_node_id.to_string()),
        produced_at: 0, // Service layer should overwrite this with `now()`
    }
}

// =========================================================================
// 5. DEPENDENCY RESOLUTION (The Wake-Up Call)
// =========================================================================

/// After data lands in a specific Projection (Inbox), this function finds
/// which Rules are waiting for that specific data.
///
/// This is the "Reverse Lookup".
pub fn find_rules_affected_by_projection(
    snapshot: &GraphSnapshot,
    updated_projection_id: &str,
) -> Vec<RuleId> {
    // In a highly optimized system, the Snapshot would have a `projection_dependents`
    // reverse-index map. For MVP, scanning the rules HashMap in Rust is extremely fast
    // (microseconds for <10k rules).

    snapshot
        .rules
        .values()
        .filter(|rule| {
            rule.input_projection_ids
                .contains(&updated_projection_id.to_string())
        })
        .map(|rule| rule.id.clone())
        .collect()
}

// --- UNIT TESTS ---
#[cfg(test)]
mod propagation_tests {
    use super::*;
    use crate::domain::enums::FiringMode;
    use crate::domain::models::RuleBlueprint;

    #[test]
    fn test_routing_and_wakeup() {
        // Setup: Rule A outputs to Projections P1 and P2.
        // Rule B needs P1. Rule C needs P2.

        let mut routes = HashMap::new();
        routes.insert(
            "RuleA".to_string(),
            vec!["P1".to_string(), "P2".to_string()],
        );

        let mut rules = HashMap::new();

        // Rule B
        rules.insert(
            "RuleB".to_string(),
            RuleBlueprint {
                id: "RuleB".to_string(),
                input_projection_ids: vec!["P1".to_string()], // Needs P1
                // ... defaults ...
                owner_node_id: "N2".to_string(),
                name: "B".into(),
                firing_mode: FiringMode::Single,
                is_terminal: false,
                prompt_template: "".into(),
                placeholder_map: HashMap::new(),
                output_ffo_ids: vec![],
            },
        );

        // Rule C
        rules.insert(
            "RuleC".to_string(),
            RuleBlueprint {
                id: "RuleC".to_string(),
                input_projection_ids: vec!["P2".to_string()], // Needs P2
                // ... defaults ...
                owner_node_id: "N3".to_string(),
                name: "C".into(),
                firing_mode: FiringMode::Single,
                is_terminal: false,
                prompt_template: "".into(),
                placeholder_map: HashMap::new(),
                output_ffo_ids: vec![],
            },
        );

        let snapshot = GraphSnapshot {
            graph_id: "G".into(),
            project_id: "P".into(),
            rules,
            routes,
            start_node_ids: vec![],
            nodes: HashMap::new(),
            ffis: HashMap::new(),
            ffos: HashMap::new(),
            projections: HashMap::new(),
        };

        // 1. Test Routing: Where does RuleA output go?
        let targets = get_downstream_projections(&snapshot, "RuleA");
        assert!(targets.contains(&"P1".to_string()));
        assert!(targets.contains(&"P2".to_string()));

        // 2. Test Wakeup: If P1 receives data, who cares?
        let affected = find_rules_affected_by_projection(&snapshot, "P1");
        assert_eq!(affected.len(), 1);
        assert_eq!(affected[0], "RuleB");

        // 3. Test Wakeup: If P2 receives data?
        let affected_c = find_rules_affected_by_projection(&snapshot, "P2");
        assert_eq!(affected_c[0], "RuleC");
    }
}
