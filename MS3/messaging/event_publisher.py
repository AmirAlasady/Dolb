from .rabbitmq_client import rabbitmq_client

class AIModelEventPublisher:
    def publish_model_deleted(self, model_id: str):
        """
        Announces that a model has been permanently deleted.
        """
        rabbitmq_client.publish(
            exchange_name='resource_events',
            routing_key='model.deleted',
            body={"model_id": model_id}
        )

    def publish_capabilities_updated(self, model_id: str, new_capabilities: list):
        """
        Announces that a model's capabilities have changed.
        """
        rabbitmq_client.publish(
            exchange_name='resource_events',
            routing_key='model.capabilities.updated',
            body={"model_id": model_id, "new_capabilities": new_capabilities}
        )
    # --- THIS IS THE MISSING/INCORRECT METHOD THAT CAUSED THE ERROR ---
    def publish_resource_for_user_deleted(self, user_id: str):
        """
        Publishes a confirmation that all AIModels for a given user
        have been successfully deleted. This is part of the User Deletion Saga.
        """
        event_name = "resource.for_user.deleted.AIModelService"
        payload = {
            "user_id": str(user_id),
            "service_name": "AIModelService" # Identifies this service as the sender
        }
        rabbitmq_client.publish(
            exchange_name='user_events', # Publishes to the user_events exchange
            routing_key=event_name,
            body=payload
        )
aimodel_event_publisher = AIModelEventPublisher()