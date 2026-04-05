from .rabbitmq_client import rabbitmq_client

class AuthEventPublisher:
    def publish_user_deletion_initiated(self, user_id):
        event_name = "user.deletion.initiated"
        payload = {"user_id": str(user_id)}
        rabbitmq_client.publish(
            exchange_name='user_events', # A new exchange for user-level events
            routing_key=event_name,
            body=payload
        )

event_publisher = AuthEventPublisher()