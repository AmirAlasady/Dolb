use serde::{Deserialize, Serialize};

/// Firing mode for a rule
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum FiringMode {
    /// Fire when ANY single input has data
    Single,
    /// Fire only when ALL inputs have data
    And,
    /// Fire when at least one input has data (same as Single for now)
    Or,
}

/// Runtime status of a rule execution
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum RuleStatus {
    /// Not yet evaluated / waiting for inputs
    Idle,
    /// Inference request has been sent to MS5/MS6
    Dispatched,
    /// Inference completed successfully
    Completed,
    /// Inference failed
    Failed,
}

/// Overall status of a graph execution run
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum RunStatus {
    /// Initial state: seeding start nodes
    Seeding,
    /// Actively executing rules
    Running,
    /// All terminal rules completed
    Completed,
    /// A critical failure occurred
    Failed,
    /// Manually terminated by user
    Canceled,
}
