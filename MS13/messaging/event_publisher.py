# MS13/messaging/event_publisher.py

import logging
from .rabbitmq_client import rabbitmq_client

logger = logging.getLogger(__name__)

class LrsEventPublisher:
    def publish_download_requested(self, model_id: str, huggingface_id: str):
        """
        Publishes an event to the message queue, requesting that the
        Asset Worker (MS14) download a model from Hugging Face.
        """
        event_name = "lrs.model.download.requested"
        payload = {
            "model_id": model_id,
            "huggingface_id": huggingface_id
        }
        
        logger.info(f"Publishing event '{event_name}' for model: {huggingface_id}")
        
        rabbitmq_client.publish(
            exchange_name='lrs_events',
            routing_key=event_name,
            body=payload,
            exchange_type='topic'
        )

# Create a single instance for the application to use
lrs_event_publisher = LrsEventPublisher()