# MS6/app/messaging/publisher.py

import json
import aio_pika
from app.logging_config import logger

class ResultPublisher:
    """
    Handles publishing all outgoing messages from the executor using aio_pika.
    This version is fully asynchronous and designed to work with an asyncio event loop.
    """
    def __init__(self, connection: aio_pika.RobustConnection):
        if not connection or connection.is_closed:
            raise ValueError("A valid, open aio_pika connection must be provided.")
        self.connection = connection

    async def _publish(self, exchange_name: str, routing_key: str, body: dict):
        """Publishes a message using a new channel from the shared connection."""
        try:
            # Create a new channel for this publishing operation
            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
                )
                message = aio_pika.Message(
                    body=json.dumps(body, default=str).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )
                await exchange.publish(message, routing_key=routing_key)
                logger.info(f"Published message to exchange '{exchange_name}' with key '{routing_key}'")
        except Exception as e:
            logger.error(f"Failed to publish to exchange '{exchange_name}': {e}", exc_info=True)

    async def publish_stream_chunk(self, job_id: str, chunk_content: str):
        """Publishes a streaming chunk of the result."""
        await self._publish(
            "results_exchange", 
            f"inference.result.streaming.{job_id}",
            {"job_id": job_id, "type": "chunk", "content": chunk_content}
        )
    
#    async def publish_final_result(self, job_id: str, result_content: str):
#        """Publishes the complete, final message."""
#        await self._publish(
#            "results_exchange", 
#            "inference.result.final", 
#            {"job_id": job_id, "status": "success", "content": result_content}
#        )
    async def publish_final_result(self, job_id: str, result_content: str, metadata: dict = None):
        """Publishes the complete, final message."""
        
        payload = {
            "job_id": job_id,
            "status": "success",
            "content": result_content
        }
        
        # --- NEW: Inject Metadata ---
        if metadata:
            # We specifically look for MS15 keys to pass back
            if "run_id" in metadata: payload["run_id"] = metadata["run_id"]
            if "rule_id" in metadata: payload["rule_id"] = metadata["rule_id"]
            if "attempt_id" in metadata: payload["attempt_id"] = metadata["attempt_id"]
            # Pass everything else too
            payload["metadata"] = metadata
        # ----------------------------

        await self._publish(
            "results_exchange", 
            "inference.result.final", 
            payload
        )
        
    async def publish_error_result(self, job_id: str, error_message: str, metadata: dict = None):
        """Publishes an error message if the job fails."""
        payload = {
            "job_id": job_id,
            "status": "error",
            "error": error_message
        }

        # --- NEW: Inject Metadata for error handling ---
        if metadata:
            if "run_id" in metadata: payload["run_id"] = metadata["run_id"]
            if "rule_id" in metadata: payload["rule_id"] = metadata["rule_id"]
            if "attempt_id" in metadata: payload["attempt_id"] = metadata["attempt_id"]
            payload["metadata"] = metadata
        # ----------------------------

        await self._publish(
            "results_exchange", 
            "inference.result.error", 
            payload
        )

    async def publish_memory_update(self, job, final_result, final_input: dict = None):
        """
        Triggers the memory feedback loop. Now checks the persistence flag.
        """
        memory_ids = job.feedback_ids
        bucket_id = memory_ids.get("memory_bucket_id")
        
        if not bucket_id:
            logger.info(f"[{job.id}] No memory_bucket_id found in job. Skipping memory update.")
            return

        logger.info(f"[{job.id}] Publisher: Preparing to publish memory update for bucket: {bucket_id}")
        logger.info(f"[{job.id}] Publisher: Job flag 'persist_inputs_in_memory' is {job.persist_inputs_in_memory}")
        
        prompt_to_save = ""
        # The logic here is correct, it just needs the correct flag value from the Job object.
        if job.persist_inputs_in_memory and final_input:
            prompt_to_save = final_input.get("input", job.prompt_text)
            logger.info(f"[{job.id}] Publisher: Persistence is ON. Saving full context to memory.")
        else:
            prompt_to_save = job.prompt_text
            logger.info(f"[{job.id}] Publisher: Persistence is OFF. Saving original prompt to memory.")
        
        user_message_content = [{"type": "text", "text": prompt_to_save}]
        
        if not job.persist_inputs_in_memory:
            for inp in job.inputs:
                if inp.get('type') == 'file_id':
                    user_message_content.append({"type": "file_ref", "file_id": inp.get('id')})

        user_message = {"role": "user", "content": user_message_content}

        assistant_message = {
            "role": "assistant",
            "content": [{"type": "text", "text": final_result}]
        }
        
        update_payload = {
            "idempotency_key": job.id,
            "memory_bucket_id": bucket_id,
            "messages_to_add": [user_message, assistant_message]
        }
        
        logger.debug(f"[{job.id}] Publisher: Final memory update payload:\n{json.dumps(update_payload, indent=2)}")
        await self._publish("memory_exchange", "memory.context.update", update_payload)