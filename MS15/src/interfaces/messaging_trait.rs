use async_trait::async_trait;
use anyhow::Result;
use crate::domain::models::{EvalCheckMessage, InferenceRequestMessage};

#[async_trait]
pub trait MessagingFacade: Send + Sync {
    async fn publish_inference_request(&self, msg: InferenceRequestMessage) -> Result<()>;
    async fn publish_eval_check(&self, msg: EvalCheckMessage) -> Result<()>;
}