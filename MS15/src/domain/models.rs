use crate::domain::enums::{FiringMode, RuleStatus, RunStatus};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

// ==========================================
// 0. TYPE ALIASES (The Vocabulary)
// ==========================================
pub type RunId = String;
pub type GraphId = String;
pub type NodeId = String;
pub type RuleId = String;
pub type ProjectionId = String;
pub type FfiId = String; // Feed-Forward Input Buffer ID
pub type FfoId = String; // Feed-Forward Output Buffer ID

// ==========================================
// 1. THE BLUEPRINT (Static Graph Definition)
// ==========================================
// This mirrors the MS14 Relational Model into a flat, fast Lookup Table structure.

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphSnapshot {
    pub graph_id: GraphId,
    pub project_id: String,

    // --- The Topology ---
    /// All Nodes in the graph, accessible by ID
    pub nodes: HashMap<NodeId, NodeBlueprint>,
    /// All Input Buffers (Mailboxes), accessible by ID
    pub ffis: HashMap<FfiId, FfiBlueprint>,
    /// All Output Buffers (Outboxes), accessible by ID
    pub ffos: HashMap<FfoId, FfoBlueprint>,
    /// All Feedback Input Buffers (Loop landing points), accessible by ID
    pub fbis: HashMap<String, FbiBlueprint>,
    /// All Logic Contexts (Projections), accessible by ID
    pub projections: HashMap<ProjectionId, ProjectionBlueprint>,

    // --- The Logic ---
    /// All Firing Rules, accessible by ID
    pub rules: HashMap<RuleId, RuleBlueprint>,

    // --- Optimization / Indexes ---
    /// List of nodes marked as 'is_start=True' for seeding
    pub start_node_ids: Vec<NodeId>,

    /// The "Fast Path" Routing Table.
    /// Maps {RuleID -> List[Destination Projection IDs]}.
    /// This allows the Propagator to skip traversing FFO->Node->FFI->Projection every time.
    pub routes: HashMap<RuleId, Vec<ProjectionId>>,
}

/// Represents a GNode (The container of logic)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeBlueprint {
    pub id: NodeId,
    pub name: String,
    pub is_start: bool,
    /// The specific AI Agent/Computation Unit definition from MS4
    pub ms4_node_id: Option<String>,
}

/// Feed-Forward Input Buffer (The "Inbox" for a Node)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FfiBlueprint {
    pub id: FfiId,
    pub owner_node_id: NodeId,  // Who receives data here?
    pub source_node_id: NodeId, // Who sends data here?
}

/// Feed-Forward Output Buffer (The "Outbox" for a Node)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FfoBlueprint {
    pub id: FfoId,
    pub owner_node_id: NodeId, // Who sends data from here?
    pub dest_node_id: NodeId,  // Who is this data going to?
}

/// Feedback Input Buffer (The landing pad for loop data)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FbiBlueprint {
    pub id: String,
    pub owner_node_id: NodeId,   // Who receives the feedback?
    pub source_node_id: NodeId,  // Which node sent the feedback (the controller)?
}

/// Represents a Semantic Input Stream (A[raw], A[i], A[x&y], ~B[x])
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectionBlueprint {
    pub id: ProjectionId,
    pub owner_node_id: NodeId,

    /// If Some, this is a forward-context projection sourced from a forward edge (FFI).
    pub source_ffi_id: Option<FfiId>,

    /// If Some, this is a feedback-context projection sourced from a feedback edge (FBI).
    /// This is what creates the ~Controller[...] context that the home-run node reads.
    pub source_fbi_id: Option<String>,

    /// If Some, this is a Derived Projection created by a specific rule.
    /// If None, this is a Base/Raw Projection (usually not selectable).
    pub produced_by_rule_id: Option<RuleId>,

    /// The list of parent projection IDs from which this derived projection was formed.
    /// Used to recursively trace FBI/feedback taints (A[~C[...]]).
    #[serde(default)]
    pub children_ids: Vec<ProjectionId>,

    pub is_selectable: bool,
}

/// Represents the Logic Gate inside a Node
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuleBlueprint {
    pub id: RuleId,
    pub owner_node_id: NodeId,
    pub name: String,

    /// The Logic: SINGLE, AND, OR
    pub firing_mode: FiringMode,

    /// If true, this rule produces a Final Graph Result and has NO outputs.
    pub is_terminal: bool,

    /// The Inputs: Ordered list of Projections this rule consumes.
    pub input_projection_ids: Vec<ProjectionId>,

    /// The Forward Outputs: List of FFOs this rule shoots data into.
    /// Present for exit/post rules that advance the graph forward.
    pub output_ffo_ids: Vec<FfoId>,

    /// The Feedback Outputs: List of FBOs this controller rule writes back to.
    /// Present for looping rules that send ~X[...] back upstream.
    /// A rule may not have both output_ffo_ids AND output_fbo_ids (controller exclusivity).
    #[serde(default)]
    pub output_fbo_ids: Vec<String>,

    /// The Context Formatter: Template to render inputs into a prompt.
    pub prompt_template: String,
    /// Maps placeholder keys ("in1", "in2") to Projection IDs.
    pub placeholder_map: HashMap<String, ProjectionId>,

    /// Loop control — only for controller rules (FBO outputs).
    /// None = agent decides when to exit.
    /// Some(N) = MS15 forces exit after N completed iterations.
    #[serde(default)]
    pub max_iterations: Option<u32>,
}

impl RuleBlueprint {
    /// Returns `true` if ALL of this rule's input projections are completely forward-context.
    /// A projection is forward-context if neither it, nor any of its ancestors,
    /// were rooted in an FBI feedback channel.
    ///
    /// Used to:
    ///   - Gate feedback-family rules until the node has been anchored
    ///   - Decide when to promote node anchor state upon successful commit
    pub fn is_forward_family(&self, snapshot: &GraphSnapshot) -> bool {
        self.input_projection_ids.iter().all(|pid| {
            is_forward_projection(snapshot, pid)
        })
    }

    /// Returns `true` if this rule is a loop controller (has at least one FBO output).
    /// Controller rules may loop back upstream and track iteration state.
    pub fn is_controller(&self) -> bool {
        !self.output_fbo_ids.is_empty()
    }
}

/// Recursively checks if a projection and all its children/ancestors
/// are free of FBI origins (feedback taints).
fn is_forward_projection(snapshot: &GraphSnapshot, pid: &str) -> bool {
    if let Some(p) = snapshot.projections.get(pid) {
        // Direct feedback origin?
        if p.source_fbi_id.is_some() {
            return false;
        }
        // Otherwise, check all children/ancestors recursively
        return p.children_ids.iter().all(|child_id| {
            is_forward_projection(snapshot, child_id)
        });
    }
    // Safe fallback if projection is somehow missing
    true
}

// ==========================================
// 2. RUNTIME STATE (Dynamic)
// ==========================================
// These objects represent the "Electricity" flowing through the circuit.

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunMetadata {
    pub run_id: RunId,
    pub graph_id: GraphId,
    pub status: RunStatus,
    pub created_at: u64, // Unix Timestamp
    pub updated_at: u64,
}

/// A "Packet" of data sitting in a Projection Buffer (Redis List).
/// This corresponds to `ms15:run:{id}:state:proj:{proj_id}`
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataPacket {
    /// The actual content (text, JSON, etc.)
    pub payload: Value,
    /// Which rule created this? (None if it's a Seed/User Input)
    pub source_rule_id: Option<RuleId>,
    /// Which node did this come from?
    pub source_node_id: Option<NodeId>,
    pub produced_at: u64,
}

/// The state of a specific rule execution attempt.
/// Corresponds to `ms15:run:{id}:state:rule:{rule_id}`
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuleRuntimeState {
    pub status: RuleStatus,
    pub attempt_count: u8,
    pub last_updated: u64,
    /// The ID of the current active inference request (for idempotency)
    pub current_attempt_id: Option<String>,
}

// ==========================================
// 3. MESSAGING CONTRACTS (Events)
// ==========================================
// Standardized JSON payloads for RabbitMQ.

/// Queue: ms15_eval_queue
/// Trigger: "Check if this rule is ready to run"
#[derive(Debug, Serialize, Deserialize)]
pub struct EvalCheckMessage {
    pub run_id: RunId,
    pub rule_id: RuleId,
    /// Debug info: what triggered this check? (e.g., "Projection P_123 received data")
    pub trigger_source: Option<String>,
}

/// Queue: inference_request_queue (To MS5)
/// Trigger: "Rule is ready, please execute logic"
#[derive(Debug, Serialize, Deserialize)]
pub struct InferenceRequestMessage {
    pub run_id: RunId,
    pub rule_id: RuleId,
    /// Used by MS5 to fetch tool/memory configs
    pub node_id: NodeId,
    /// The actual AI Agent Definition from MS4
    pub ms4_node_id: Option<String>,
    /// Traceability ID for this specific execution attempt
    pub attempt_id: String,
    /// The fully rendered text prompt (placeholders resolved)
    pub prompt_text: String,
    /// Passthrough flags (e.g. source=graph_execution) to control MS8/MS9 behavior
    pub metadata: HashMap<String, Value>,
}

/// Queue: inference_result_queue (From MS6)
/// Trigger: "Execution finished"
#[derive(Debug, Serialize, Deserialize)]
pub struct InferenceResultMessage {
    #[serde(default)]
    pub run_id: RunId,
    #[serde(default)]
    pub rule_id: RuleId,
    #[serde(default)]
    pub attempt_id: String,
    pub status: String, // "success" or "error"
    /// MS6 sends this as "content", we alias it
    #[serde(alias = "content", default)]
    pub payload: Option<Value>,
    pub error: Option<String>,
    /// MS6 also includes full metadata
    #[serde(default)]
    pub metadata: Option<HashMap<String, Value>>,
}
