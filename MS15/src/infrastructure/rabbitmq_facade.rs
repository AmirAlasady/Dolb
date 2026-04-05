use async_trait::async_trait;
use lapin::{
    options::*, types::FieldTable, BasicProperties, Connection, ConnectionProperties, Channel
};
use anyhow::{Result, Context};

use crate::domain::models::{EvalCheckMessage, InferenceRequestMessage};
use crate::interfaces::messaging_trait::MessagingFacade;

pub struct RabbitMQAdapter {
    #[allow(dead_code)] // Keep connection alive
    connection: Connection,
    pub channel: Channel,
}

impl RabbitMQAdapter {
    pub async fn new(url: &str) -> Result<Self> {
        let connection = Connection::connect(url, ConnectionProperties::default()).await
            .context("Failed to connect to RabbitMQ")?;
            
        let channel = connection.create_channel().await
            .context("Failed to create RabbitMQ channel")?;

        channel.exchange_declare(
            "ms15_events", lapin::ExchangeKind::Topic, 
            ExchangeDeclareOptions{ durable: true, ..Default::default() }, FieldTable::default()
        ).await?;

        channel.exchange_declare(
            "inference_exchange", lapin::ExchangeKind::Topic, 
            ExchangeDeclareOptions{ durable: true, ..Default::default() }, FieldTable::default()
        ).await?;

        // --- Declare Queues & Bind to Exchanges ---
        // ms15_eval_queue: receives "check this rule" commands from Trigger & Propagator
        channel.queue_declare(
            "ms15_eval_queue",
            QueueDeclareOptions { durable: true, ..Default::default() },
            FieldTable::default()
        ).await?;
        channel.queue_bind(
            "ms15_eval_queue", "ms15_events", "ms15.eval.check",
            QueueBindOptions::default(), FieldTable::default()
        ).await?;

        // inference_result_queue: receives completed inference results from MS6
        // IMPORTANT: MS6 publishes to 'results_exchange', not 'inference_exchange'
        channel.exchange_declare(
            "results_exchange", lapin::ExchangeKind::Topic, 
            ExchangeDeclareOptions{ durable: true, ..Default::default() }, FieldTable::default()
        ).await?;

        channel.queue_declare(
            "inference_result_queue",
            QueueDeclareOptions { durable: true, ..Default::default() },
            FieldTable::default()
        ).await?;
        channel.queue_bind(
            "inference_result_queue", "results_exchange", "inference.result.*",
            QueueBindOptions::default(), FieldTable::default()
        ).await?;

        Ok(Self { connection, channel })
    }
}

#[async_trait]
impl MessagingFacade for RabbitMQAdapter {
    async fn publish_eval_check(&self, msg: EvalCheckMessage) -> Result<()> {
        let payload = serde_json::to_vec(&msg)?;
        self.channel.basic_publish(
            "ms15_events", "ms15.eval.check", 
            BasicPublishOptions::default(), &payload,
            BasicProperties::default().with_delivery_mode(2),
        ).await?.await?;
        Ok(())
    }

    async fn publish_inference_request(&self, msg: InferenceRequestMessage) -> Result<()> {
        let payload = serde_json::to_vec(&msg)?;
        self.channel.basic_publish(
            "inference_exchange", "inference.request",
            BasicPublishOptions::default(), &payload,
            BasicProperties::default().with_delivery_mode(2),
        ).await?.await?;
        Ok(())
    }
}