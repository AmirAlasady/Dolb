use thiserror::Error;

#[derive(Error, Debug)]
pub enum DomainError {
    #[error("Graph Run '{0}' does not exist or has expired")]
    RunNotFound(String),

    #[error("Rule '{0}' not found in the blueprint for this run")]
    RuleNotFound(String),

    #[error("Projection '{0}' not found in the blueprint")]
    ProjectionNotFound(String),

    #[error("Cannot fire Rule '{0}': Inputs are not satisfied")]
    RuleNotReady(String),

    #[error("Failed to acquire lock for Rule '{0}' (Concurrency limit or Race condition)")]
    LockAcquisitionFailed(String),

    #[error("Rule '{0}' has already been fired or is currently running")]
    RuleAlreadyDispatched(String),

    #[error("Invalid state transition for Rule '{0}': Cannot go from {1:?} to {2:?}")]
    InvalidStateTransition(String, String, String),

    #[error("Data corruption: {0}")]
    DataCorruption(String),

    // --- Wrapper Errors (for when Infra leaks into Domain logic) ---
    #[error("Serialization failure: {0}")]
    SerializationError(#[from] serde_json::Error),
}