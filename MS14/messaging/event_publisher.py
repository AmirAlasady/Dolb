# MS14/messaging/event_publisher.py

from .rabbitmq_client import rabbitmq_client
import logging

logger = logging.getLogger(__name__)

class GraphEventPublisher:
    def publish_graphs_for_project_deleted(self, project_id: str):
        """
        Publishes a confirmation that all Graphs for a given Project
        have been successfully deleted, fulfilling its part of the saga.
        """
        event_name = "resource.for_project.deleted.GraphService"
        payload = {
            "project_id": str(project_id),
            "service_name": "GraphService"
        }
        
        try:
            rabbitmq_client.publish(
                exchange_name='project_events',
                routing_key=event_name,
                body=payload
            )
            logger.info(f"Published confirmation event: {event_name} for project {project_id}")
        except Exception as e:
            logger.error(f"Failed to publish confirmation event for project {project_id}: {e}")

# Create a single instance for the application to use
graph_event_publisher = GraphEventPublisher()
