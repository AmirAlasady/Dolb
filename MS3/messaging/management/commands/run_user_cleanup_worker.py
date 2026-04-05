import pika
import json
import time
from django.core.management.base import BaseCommand

# Import the model from the aimodels app and the publisher from the messaging app
from aimodels.models import AIModel
from messaging.event_publisher import aimodel_event_publisher
from django.conf import settings

def handle_user_deletion(user_id: str):
    """
    The core business logic for cleaning up all user-owned AIModels.
    This function is idempotent, meaning running it multiple times for the
    same user_id will not cause errors.
    """
    print(f" [!] Received request to delete AIModels for user: {user_id}")
    
    # Use the Django ORM to find and delete all non-system models owned by this user.
    models_to_delete = AIModel.objects.filter(
        owner_id=user_id, 
        is_system_model=False
    )
    
    deleted_count = models_to_delete.count()
    if deleted_count > 0:
        models_to_delete.delete()
    
    print(f" [✓] Deleted {deleted_count} user-owned AIModels for user {user_id}.")
    
    # After successful deletion, publish the confirmation event.
    # This happens even if the user had 0 models, to signal completion.
    aimodel_event_publisher.publish_resource_for_user_deleted(user_id)


class Command(BaseCommand):
    """
    Django management command to run a RabbitMQ worker.
    This worker listens for `user.deletion.initiated` events and cleans up
    all associated user-owned AIModel configurations.
    """
    help = 'Runs a RabbitMQ worker to listen for user deletion events.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL

        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()

                # This worker listens to the user_events exchange.
                channel.exchange_declare(exchange='user_events', exchange_type='topic', durable=True)
                
                # A durable queue for this specific worker.
                queue_name = 'aimodel_user_cleanup_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                # Bind the queue to listen for the specific user deletion event.
                routing_key = 'user.deletion.initiated'
                channel.queue_bind(exchange='user_events', queue=queue_name, routing_key=routing_key)

                self.stdout.write(self.style.SUCCESS(' [*] AIModel user cleanup worker waiting for messages. To exit press CTRL+C'))

                def callback(ch, method, properties, body):
                    try:
                        data = json.loads(body)
                        user_id = data.get('user_id')

                        if user_id:
                            # Call the main handler function with the user_id.
                            handle_user_deletion(user_id)
                        else:
                            self.stderr.write(self.style.WARNING(f" [!] Received message without user_id: {body}"))
                    
                    except json.JSONDecodeError:
                        self.stderr.write(self.style.ERROR(f" [!] Could not decode message body: {body}"))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f" [!] An unexpected error occurred: {e}"))
                        # Add nack logic for production systems here.
                    
                    # Acknowledge the message was processed (or failed in a way we won't retry).
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                channel.basic_consume(queue=queue_name, on_message_callback=callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError:
                self.stderr.write(self.style.ERROR('Connection to RabbitMQ failed. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS(' [!] Stopping worker...'))
                if 'connection' in locals() and connection.is_open:
                    connection.close()
                break