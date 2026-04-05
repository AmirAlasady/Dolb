# MS11/messaging/event_publisher.py

import logging
from .rabbitmq_client import rabbitmq_client

logger = logging.getLogger(__name__)

class RagEventPublisher:
    def publish_ingestion_requested(self, **kwargs):
        """
        Publishes an event to request the asynchronous ingestion of a file
        into a knowledge collection.
        
        Args:
            **kwargs: A dictionary containing all necessary details for the
                      ingestion worker, e.g., link_id, collection_id, file_id,
                      user_id, strategy_type, etc.
        """
        logger.info(f"Publishing event 'rag.ingestion.requested' for file_id: {kwargs.get('file_id')}")
        rabbitmq_client.publish(
            exchange_name='rag_events',
            routing_key='rag.ingestion.requested',
            body=kwargs
        )
    
    def publish_project_cleanup_confirmation(self, project_id: str):
        """
        Publishes a confirmation that all KnowledgeCollections for a given project
        have been successfully deleted. This is part of the Project Deletion Saga.
        """
        event_name = "resource.for_project.deleted.RAGService"
        payload = {
            "project_id": str(project_id),
            "service_name": "RAGService" # Identifies this service as the sender
        }
        
        logger.info(f"Publishing project cleanup confirmation for project_id: {project_id}")
        rabbitmq_client.publish(
            exchange_name='project_events',
            routing_key=event_name,
            body=payload
        )
    def publish_collection_deleted(self, collection_id: str, owner_id: str):
        """
        Announces that a KnowledgeCollection has been permanently deleted,
        so that dependent services like the Node Service can react.
        """
        event_name = "rag.collection.deleted"
        payload = {
            "collection_id": str(collection_id),
            "owner_id": str(owner_id) # Good practice to include for logging/auditing
        }
        logger.info(f"Publishing event '{event_name}' for collection_id: {collection_id}")
        rabbitmq_client.publish(
            exchange_name='resource_events', # Use the shared exchange for all resources
            routing_key=event_name,
            body=payload
        )
# Create a single instance for the application to use
rag_event_publisher = RagEventPublisher()