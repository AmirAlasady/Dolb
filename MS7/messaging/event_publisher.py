from .rabbitmq_client import rabbitmq_client

class ToolEventPublisher:
    def publish_resource_for_user_deleted(self, user_id: str):
        event_name = "resource.for_user.deleted.ToolService"
        payload = {
            "user_id": str(user_id),
            "service_name": "ToolService"
        }
        rabbitmq_client.publish(
            exchange_name='user_events',
            routing_key=event_name,
            body=payload
        )
    def publish_tool_deleted(self, tool_id: str):
        rabbitmq_client.publish(
            exchange_name='resource_events',
            routing_key='tool.deleted',
            body={"tool_id": tool_id}
        )
tool_event_publisher = ToolEventPublisher()