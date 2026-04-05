# MS9/messaging/event_publisher.py
from .rabbitmq_client import rabbitmq_client

class MemoryEventPublisher:
    def publish_bucket_deleted(self, bucket_id: str):
        rabbitmq_client.publish(
            exchange_name='resource_events',
            routing_key='memory.bucket.deleted',
            body={"bucket_id": bucket_id}
        )
    
    def publish_project_cleanup_confirmation(self, project_id: str):
        rabbitmq_client.publish(
            exchange_name='project_events',
            routing_key='resource.for_project.deleted.MemoryService',
            body={"project_id": project_id, "service_name": "MemoryService"}
        )

memory_event_publisher = MemoryEventPublisher()