# MS10/messaging/event_publisher.py

import logging
from .rabbitmq_client import rabbitmq_client

logger = logging.getLogger(__name__)

class DataEventPublisher:
    def publish_project_cleanup_confirmation(self, project_id: str):
        """
        Publishes a confirmation that all StoredFile objects for a given Project
        have been successfully deleted, fulfilling this service's part of the saga.
        """
        event_name = "resource.for_project.deleted.DataService"
        payload = {
            "project_id": str(project_id),
            "service_name": "DataService" # Identifies this service as the sender
        }
        
        logger.info(f"Publishing project cleanup confirmation for project_id: {project_id}")
        
        rabbitmq_client.publish(
            exchange_name='project_events',
            routing_key=event_name,
            body=payload,
            exchange_type='topic'
        )

# Create a single instance for the application to use
data_event_publisher = DataEventPublisher()