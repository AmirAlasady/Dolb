# in project_service/messaging/event_publisher.py
from .rabbitmq_client import rabbitmq_client

class EventPublisher:
    """A dedicated class for publishing business-specific events."""

    def publish_project_deletion_initiated(self, project_id, owner_id):
        event_name = "project.deletion.initiated"
        payload = {
            "project_id": str(project_id),
            "owner_id": str(owner_id)
        }
        rabbitmq_client.publish(
            exchange_name='project_events',
            routing_key=event_name,
            body=payload
        )
    def publish_all_projects_for_user_deleted(self, user_id):
        event_name = "all_projects_for_user.deleted"
        payload = {"user_id": str(user_id)}
        rabbitmq_client.publish(
            exchange_name='user_events', # Publish to the user_events exchange
            routing_key=event_name,
            body=payload
        )
# Create an instance to be used by the service layer
event_publisher = EventPublisher()