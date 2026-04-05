// Logic: Setup Run -> Start
use std::collections::HashMap;
use std::sync::Arc;
use uuid::Uuid;
use anyhow::{Result, Context};
use std::time::{SystemTime, UNIX_EPOCH};
use serde_json::Value;

// Fix: Import RunStatus explicitly
use crate::domain::enums::RunStatus;
use crate::domain::models::{
    RunId, GraphId, RunMetadata, DataPacket, EvalCheckMessage,
};
// ..
use crate::interfaces::storage_trait::StorageFacade;
use crate::interfaces::messaging_trait::MessagingFacade;
use crate::infrastructure::ms14_client::Ms14Client;

pub struct TriggerService<S, M> {
    storage: Arc<S>,
    messaging: Arc<M>,
    ms14_client: Ms14Client, // Concrete client is fine here as it's specific to this service
}

impl<S: StorageFacade, M: MessagingFacade> TriggerService<S, M> {
    pub fn new(storage: Arc<S>, messaging: Arc<M>, ms14_url: String) -> Self {
        Self {
            storage,
            messaging,
            ms14_client: Ms14Client::new(ms14_url),
        }
    }

    /// Starts a new execution run.
    /// 
    /// # Arguments
    /// * `graph_id`: The ID of the graph to run.
    /// * `user_inputs`: Map of { NodeID -> InputValue } for the start nodes.
    /// * `jwt_token`: Passed through to MS14 for auth.
    pub async fn start_run(
        &self, 
        graph_id: GraphId, 
        user_inputs: HashMap<String, Value>, 
        jwt_token: &str,
        user_id: &str,
    ) -> Result<RunId> {
        // 1. Generate Run ID
        let run_id = Uuid::new_v4().to_string();
        let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();

        // 2. Fetch Blueprint from MS14
        println!("--> Fetching snapshot for graph {}", graph_id);
        let snapshot = self.ms14_client.fetch_graph_snapshot(&graph_id, jwt_token).await?;

        // CASE 1: Must have at least one rule to execute
        if snapshot.rules.is_empty() {
             anyhow::bail!("Cannot start run for graph {}: No rules defined. A valid graph must have at least one rule.", graph_id);
        }

        // 3. Save Run Metadata to Redis
        let _meta = RunMetadata {
            run_id: run_id.clone(),
            graph_id: graph_id.clone(),
            status: RunStatus::Seeding, // Transition state
            created_at: now,
            updated_at: now,
        };

        // 4. Save Blueprint to Redis (The "Circuit Board").
        self.storage.save_blueprint(&run_id, &snapshot).await
            .context("Failed to save graph blueprint to Redis")?;

        // 4b. Store user_id alongside the run so evaluator/propagator can access it
        self.storage.save_run_user_id(&run_id, user_id).await
            .context("Failed to save run user_id")?;

        // 5. Seed Start Nodes
        println!("--> Seeding {} start nodes with {} user inputs", snapshot.start_node_ids.len(), user_inputs.len());

        for (node_id, input_value) in user_inputs {
            // Find the seed projection for this node from the snapshot
            // A seed projection is one owned by a start node with NO sources of any kind.
            if let Some(proj) = snapshot.projections.values().find(|p| {
                p.owner_node_id == node_id && 
                p.source_ffi_id.is_none() &&
                p.source_fbi_id.is_none() &&
                p.produced_by_rule_id.is_none()
            }) {
                
                let packet = DataPacket {
                    payload: input_value,
                    source_rule_id: None, // User input has no rule source
                    source_node_id: None,
                    produced_at: now,
                };

                // Push to Redis Buffer
                self.storage.push_data_to_projection(&run_id, &proj.id, &packet).await?;
                
                // 6. Trigger Evaluation for this Node's Rules
                let rules_on_node: Vec<&str> = snapshot.rules.values()
                    .filter(|r| r.owner_node_id == node_id)
                    .map(|r| r.id.as_str())
                    .collect();
                
                println!("  --> Found {} rules on start node {}", rules_on_node.len(), node_id);
                     
                for rid in rules_on_node {
                    let event = EvalCheckMessage {
                        run_id: run_id.clone(),
                        rule_id: rid.to_string(),
                        trigger_source: Some("User Seed".into()),
                    };
                    self.messaging.publish_eval_check(event).await?;
                    println!("  --> Published eval check for rule {}", rid);
                }
            } else {
                println!("  ⚠️  No seed projection found for start node {}", node_id);
            }
        }

        // 7. Update Status to Running
        self.storage.set_run_status(&run_id, RunStatus::Running).await?;

        println!("--> Run {} started successfully.", run_id);
        Ok(run_id)
    }
}
