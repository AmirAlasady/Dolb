use std::sync::Arc;
use std::env;
use dotenv::dotenv;
use futures_util::stream::StreamExt;
use lapin::options::{BasicAckOptions, BasicQosOptions, BasicConsumeOptions};
use lapin::types::FieldTable;

use ms15::infrastructure::{redis_facade::RedisAdapter, rabbitmq_facade::RabbitMQAdapter};
use ms15::services::propagator::PropagatorService;
use ms15::domain::models::InferenceResultMessage;

#[tokio::main]
async fn main() {
    dotenv().ok();

    let redis_url = env::var("REDIS_URL").expect("REDIS_URL required");
    let rabbit_url = env::var("RABBITMQ_URL").expect("RABBITMQ_URL required");

    println!("📡 Propagator Worker Starting...");

    // 1. Setup
    let redis = Arc::new(RedisAdapter::new(&redis_url).unwrap());
    let rabbit_adapter = Arc::new(RabbitMQAdapter::new(&rabbit_url).await.unwrap());
    let propagator = PropagatorService::new(redis, rabbit_adapter.clone());

    // 2. Get channel for consuming
    let channel = rabbit_adapter.channel.clone();
    channel.basic_qos(20, BasicQosOptions::default()).await.unwrap();

    // Note: Queue name must match what MS6 publishes to.
    // (RabbitMQAdapter constructor handles exchange topology declaration)
    let mut consumer = channel.basic_consume(
        "inference_result_queue",
        "propagator_worker",
        BasicConsumeOptions::default(),
        FieldTable::default()
    ).await.unwrap();

    println!("✅ Listening on 'inference_result_queue'");


    while let Some(delivery) = consumer.next().await {
        if let Ok(delivery) = delivery {
            let svc = propagator.clone();
            
            tokio::spawn(async move {
                let payload_bytes = &delivery.data;
                println!("📨 Received inference result: {}", String::from_utf8_lossy(payload_bytes));
                match serde_json::from_slice::<InferenceResultMessage>(payload_bytes) {
                    Ok(msg) => {
                        match svc.process_result(msg).await {
                            Ok(_) => {
                                delivery.ack(BasicAckOptions::default()).await.ok();
                            }
                            Err(e) => {
                                eprintln!("❌ Propagation Error: {:?}", e);
                                // Serious errors (Redis down) might need Nack/Retry
                                delivery.ack(BasicAckOptions::default()).await.ok();
                            }
                        }
                    }
                    Err(e) => {
                        eprintln!("⚠️  Bad JSON in result queue: {:?}", e);
                        delivery.ack(BasicAckOptions::default()).await.ok();
                    }
                }
            });
        }
    }
}