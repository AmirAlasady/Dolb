# MS6/app/messaging/cancellation_listener.py

import asyncio
import json
import aio_pika
from app import config
from app.logging_config import logger
from .worker import RUNNING_JOBS # Import the global task dictionary

class CancellationListener:
    """
    Listens for broadcasted cancellation events. When an event is received,
    it checks if the job is running on THIS instance, performs a final
    authorization check, and then cancels the asyncio.Task if valid.
    """
    async def run(self):
        """Connects to RabbitMQ and consumes cancellation messages."""
        while True:
            try:
                connection = await aio_pika.connect_robust(config.RABBITMQ_URL)
                async with connection:
                    channel = await connection.channel()
                    
                    # Declare the FANOUT exchange. It must match the one MS5 publishes to.
                    exchange = await channel.declare_exchange(
                        'job_control_fanout_exchange', 
                        aio_pika.ExchangeType.FANOUT, 
                        durable=True
                    )
                    
                    # Declare an exclusive queue. It gets a unique name and is deleted on disconnect.
                    # This ensures each MS6 instance gets its own copy of the broadcast.
                    queue = await channel.declare_queue(exclusive=True)
                    
                    # Bind our unique queue to the fanout exchange.
                    await queue.bind(exchange)
                    
                    logger.info(f" [*] Cancellation Listener is waiting for broadcast messages on unique queue '{queue.name}'.")
                    await queue.consume(self.on_message)
                    await asyncio.Event().wait() # Wait forever
            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.error(f"Cancellation Listener lost RabbitMQ connection: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

    async def on_message(self, message: aio_pika.IncomingMessage):
        """Callback to handle a broadcasted cancellation message."""
        # Acknowledge the message immediately. We don't want to requeue broadcasts.
        async with message.process(requeue=False):
            try:
                payload = json.loads(message.body.decode())
                job_id = payload.get("job_id")
                requesting_user_id = payload.get("user_id") # User who sent the DELETE request

                if not job_id or not requesting_user_id:
                    # Malformed message, ignore silently.
                    return

                # Check if the job is running on THIS instance.
                job_info = RUNNING_JOBS.get(job_id)

                if job_info:
                    # Job found locally. Now perform the authorization check.
                    owning_user_id = job_info["job"].user_id
                    
                    logger.info(f"[{job_id}] Received cancellation broadcast. Checking authorization...")
                    logger.info(f"    Job Owner: {owning_user_id} | Requesting User: {requesting_user_id}")

                    if str(owning_user_id) == str(requesting_user_id):
                        # --- AUTHORIZATION PASSED ---
                        task_to_cancel = job_info["task"]
                        task_to_cancel.cancel()
                        logger.warning(f"[{job_id}] AUTHORIZED. CANCEL INTERRUPT SENT to local task.")
                    else:
                        # --- AUTHORIZATION FAILED ---
                        logger.error(f"[{job_id}] UNAUTHORIZED cancellation attempt by user {requesting_user_id} on a job owned by {owning_user_id}. Ignoring.")

                # If job_info is None, this instance is not running the job, so we do nothing.

            except Exception as e:
                logger.error(f"Failed to process cancellation broadcast message: {e}", exc_info=True)