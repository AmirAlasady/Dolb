use std::sync::Arc;
use std::env;
use dotenv::dotenv;
use futures_util::stream::StreamExt;
use lapin::options::{BasicAckOptions, BasicQosOptions, BasicConsumeOptions};
use lapin::types::FieldTable;

use ms15::infrastructure::{redis_facade::RedisAdapter, rabbitmq_facade::RabbitMQAdapter};
use ms15::services::evaluator::EvaluatorService;
use ms15::domain::models::EvalCheckMessage;

#[tokio::main]
async fn main() {
    dotenv().ok();
    
    let redis_url = env::var("REDIS_URL").expect("REDIS_URL required");
    let rabbit_url = env::var("RABBITMQ_URL").expect("RABBITMQ_URL required");

    println!("🛠️  Evaluator Worker Starting...");

    let redis = Arc::new(RedisAdapter::new(&redis_url).unwrap());
    
    // FIX: Wrap in Arc immediately
    let rabbit_adapter = Arc::new(RabbitMQAdapter::new(&rabbit_url).await.unwrap());
    
    // Create service
    let evaluator = EvaluatorService::new(redis, rabbit_adapter.clone());

    // FIX: Clone the channel from the Arc payload
    let channel = rabbit_adapter.channel.clone(); 
    channel.basic_qos(20, BasicQosOptions::default()).await.unwrap();

    let mut consumer = channel.basic_consume(
        "ms15_eval_queue", 
        "evaluator_worker", 
        BasicConsumeOptions::default(), 
        FieldTable::default()
    ).await.unwrap();

    println!("✅ Listening on 'ms15_eval_queue'");

    while let Some(delivery) = consumer.next().await {
        if let Ok(delivery) = delivery {
            let evaluator = evaluator.clone();
            
            tokio::spawn(async move {
                let payload_bytes = &delivery.data;
                println!("📨 Received eval check: {}", String::from_utf8_lossy(payload_bytes));
                match serde_json::from_slice::<EvalCheckMessage>(payload_bytes) {
                    Ok(msg) => {
                        match evaluator.process_check(msg).await {
                            Ok(_) => { delivery.ack(BasicAckOptions::default()).await.ok(); }
                            Err(e) => {
                                eprintln!("❌ Evaluation Error: {:?}", e);
                                delivery.ack(BasicAckOptions::default()).await.ok(); 
                            }
                        }
                    }
                    Err(e) => {
                        eprintln!("⚠️  Bad JSON in eval queue: {:?}", e);
                        delivery.ack(BasicAckOptions::default()).await.ok();
                    }
                }
            });
        }
    }
}
