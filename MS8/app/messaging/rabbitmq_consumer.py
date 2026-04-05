import asyncio
import json
import aio_pika
from app import config
from app.logging_config import logger
from app.server.connection_manager import manager

class RabbitMQConsumer:
    """
    Consumes messages from the results exchange and routes them
    to the correct WebSocket via the ConnectionManager.
    """
    async def run(self):
        while True:
            try:
                connection = await aio_pika.connect_robust(config.RABBITMQ_URL)
                async with connection:
                    channel = await connection.channel()
                    
                    exchange_name = 'results_exchange'
                    await channel.declare_exchange(exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
                    
                    # Declare an exclusive queue. If this worker dies, the queue is deleted.
                    # When it restarts, it gets a fresh one. Good for load balancing.
                    queue = await channel.declare_queue(exclusive=True)
                    
                    # Listen for all result messages
                    await queue.bind(exchange_name, 'inference.result.#')
                    
                    logger.info(" [*] RabbitMQ consumer is waiting for result messages.")
                    await queue.consume(self.on_message)
                    
                    await asyncio.Event().wait()
            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection lost: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)

    async def on_message(self, message: aio_pika.IncomingMessage):
        """Callback for processing a message from the results queue."""
        async with message.process():
            try:
                message_body_bytes = message.body
                body = json.loads(message.body.decode())
                metadata = body.get("metadata", {})
                source = metadata.get("source")

                if source == "graph_execution":
                    logger.info(f"Ignoring graph execution result for job {body.get('job_id')}")
                    return
                    
                job_id = body.get("job_id")
                
                if not job_id:
                    logger.warning(f"Received message without job_id: {body}")
                    return

                redis_key = f"job:result:{job_id}"
                
                # Use a pipeline for atomic operations
                pipe = config.redis_client.pipeline()
                # RPUSH adds the message to the end of the list
                pipe.rpush(redis_key, message_body_bytes) 
                # Set a 5-minute expiry on the key every time we add to it
                pipe.expire(redis_key, 300) 
                pipe.execute()
                
                logger.info(f"Cached message for job_id: {job_id} in Redis.")
                await manager.send_message(job_id, body)

                # If the job is finished, close the connection
                if body.get("status") in ["success", "error"]:
                    await manager.close_connection(job_id)

            except json.JSONDecodeError:
                logger.error(f"Could not decode result message body: {message.body.decode()[:200]}")
            except Exception as e:
                logger.error("Error processing result message", exc_info=True)