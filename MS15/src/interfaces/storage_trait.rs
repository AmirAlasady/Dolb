use async_trait::async_trait;
use anyhow::Result;
use crate::domain::models::{RuleBlueprint, DataPacket, GraphSnapshot};
use crate::domain::enums::{RuleStatus, RunStatus};

#[async_trait]
pub trait StorageFacade: Send + Sync {
    // Reads
    async fn get_node_rules(&self, run_id: &str, node_id: &str) -> Result<Vec<String>>;
    async fn get_rule_blueprint(&self, run_id: &str, rule_id: &str) -> Result<RuleBlueprint>;
    async fn get_routes(&self, run_id: &str, rule_id: &str) -> Result<Vec<String>>;
    
    // Input Data
    async fn has_input_data(&self, run_id: &str, projection_id: &str) -> Result<bool>;
    async fn get_input_data(&self, run_id: &str, projection_id: &str) -> Result<Vec<DataPacket>>;
    
    // Writes / Mutations
    async fn lock_rule(&self, run_id: &str, rule_id: &str) -> Result<bool>;
    /// Release the lock so the evaluator can re-dispatch a retrying rule.
    async fn unlock_rule(&self, run_id: &str, rule_id: &str) -> Result<()>;
    async fn set_rule_status(&self, run_id: &str, rule_id: &str, status: RuleStatus) -> Result<()>;
    async fn push_data_to_projection(&self, run_id: &str, projection_id: &str, packet: &DataPacket) -> Result<()>;
    
    // Trigger Service needs these:
    async fn save_blueprint(&self, run_id: &str, snapshot: &GraphSnapshot) -> Result<()>;
    
    // Evaluator needs these:
    async fn get_rule_status(&self, run_id: &str, rule_id: &str) -> Result<RuleStatus>;
    
    // Propagator needs these:
    async fn get_full_snapshot(&self, run_id: &str) -> Result<GraphSnapshot>;

    // User identity (for MS5 → MS4 permission checks)
    async fn save_run_user_id(&self, run_id: &str, user_id: &str) -> Result<()>;
    async fn get_run_user_id(&self, run_id: &str) -> Result<String>;

    // Run-level status tracking
    async fn set_run_status(&self, run_id: &str, status: RunStatus) -> Result<()>;
    async fn get_run_status(&self, run_id: &str) -> Result<RunStatus>;

    /// Deletes all data associated with this run from Redis
    async fn cleanup_run(&self, run_id: &str) -> Result<()>;

    /// Retry counter: how many times has this rule been attempted?
    async fn get_rule_attempt_count(&self, run_id: &str, rule_id: &str) -> Result<u32>;
    /// Atomically increment the rule attempt counter and return the new count.
    async fn incr_rule_attempt_count(&self, run_id: &str, rule_id: &str) -> Result<u32>;

    // --- Anchor Gate ---
    /// Mark a node as "anchored" in this run (idempotent — once anchored, always anchored).
    /// Called by the propagator after a forward-family rule successfully commits.
    async fn set_node_anchored(&self, run_id: &str, node_id: &str) -> Result<()>;

    /// Returns true if the node has been anchored (i.e., at least one forward-family
    /// rule has committed on this node in this run).
    /// Used by the evaluator to gate feedback-family rules.
    async fn is_node_anchored(&self, run_id: &str, node_id: &str) -> Result<bool>;

    // --- Loop / Iteration State ---

    /// Get the current completed-iteration count for a controller rule.
    /// Returns 0 if this controller hasn't finished any iteration yet.
    async fn get_loop_iteration(&self, run_id: &str, rule_id: &str) -> Result<u32>;

    /// Atomically increment the loop iteration counter for a controller rule.
    /// Returns the NEW value after incrementing.
    async fn incr_loop_iteration(&self, run_id: &str, rule_id: &str) -> Result<u32>;

    /// Save the baseline payload (SLICE_X0) for a controller rule.
    /// Called once, the first time a controller fires, before any loop iteration completes.
    async fn save_loop_baseline(&self, run_id: &str, rule_id: &str, payload: &str) -> Result<()>;

    /// Get the saved baseline payload for a controller rule.
    async fn get_loop_baseline(&self, run_id: &str, rule_id: &str) -> Result<String>;

    /// Reset a controller rule back to Idle and remove its lock so it can fire again
    /// in the next loop iteration. Also resets attempt count.
    async fn reset_rule_for_refire(&self, run_id: &str, rule_id: &str) -> Result<()>;
}