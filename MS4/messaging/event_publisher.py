# MS4/messaging/event_publisher.py

from .rabbitmq_client import rabbitmq_client

class NodeEventPublisher:
    def publish_nodes_for_project_deleted(self, project_id: str):
        """
        Publishes a confirmation that all Nodes for a given Project
        have been successfully deleted, fulfilling its part of the saga.
        """
        event_name = "resource.for_project.deleted.NodeService"
        payload = {
            "project_id": str(project_id),
            "service_name": "NodeService"
        }
        rabbitmq_client.publish(
            exchange_name='project_events',
            routing_key=event_name,
            body=payload
        )

# Create a single instance for the application to use
node_event_publisher = NodeEventPublisher()