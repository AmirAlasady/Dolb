# MS10/messaging/management/commands/run_project_cleanup_worker.py

import pika
import json
import time
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction

# Import the model from the data app and the publisher from this messaging app
from data.models import StoredFile
from messaging.event_publisher import data_event_publisher

# Configure logging specifically for this worker
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS10-CleanupWorker - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def handle_project_cleanup(project_id: str):
    """
    The core business logic for cleaning up all files associated with a project.
    This is idempotent and transactional.
    """
    logger.info(f"--- Project Cleanup Initiated for project_id: {project_id} ---")
    
    try:
        with transaction.atomic():
            # Find all file metadata records for the project to be deleted.
            files_to_delete = StoredFile.objects.filter(project_id=project_id)
            
            if not files_to_delete.exists():
                logger.info(f"No files found for project {project_id}. Cleanup is already complete.")
            else:
                logger.info(f"Found {files_to_delete.count()} file(s) to delete for project {project_id}.")
                
                # First, delete the physical files from object storage.
                for file_record in files_to_delete:
                    storage_path = file_record.storage_path
                    if default_storage.exists(storage_path):
                        logger.info(f"Deleting file from object storage: {storage_path}")
                        default_storage.delete(storage_path)
                    else:
                        logger.warning(f"File not found in object storage, but metadata exists: {storage_path}")
                
                # If all physical deletions succeed, delete the database records in bulk.
                deleted_count, _ = files_to_delete.delete()
                logger.info(f"Successfully deleted {deleted_count} file metadata records from the database.")

        # After the transaction is successfully committed, publish the confirmation event.
        # This happens even if the project had 0 files, to signal completion to the saga orchestrator.
        data_event_publisher.publish_project_cleanup_confirmation(project_id)
        logger.info(f"--- Project Cleanup Finished for project_id: {project_id} ---")

    except Exception as e:
        logger.critical(f"CRITICAL ERROR during cleanup for project {project_id}: {e}", exc_info=True)
        # In a production system, you might want to publish a failure event here
        # or have a separate monitoring system to catch these critical log messages.
        # The transaction will be rolled back automatically on exception.

class Command(BaseCommand):
    """
    Django management command to run a RabbitMQ worker. This worker listens for
    `project.deletion.initiated` events and cleans up all associated StoredFile objects.
    """
    help = 'Runs the Data Service worker for project cleanup sagas.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL
        self.stdout.write(self.style.SUCCESS("--- Data Service Project Cleanup Worker ---"))
        self.stdout.write(f"Connecting to RabbitMQ at {rabbitmq_url}...")
        
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()

                # This worker listens to the exchange where project-level sagas are announced.
                channel.exchange_declare(exchange='project_events', exchange_type='topic', durable=True)
                
                # A durable queue specific to this worker's function.
                queue_name = 'data_project_cleanup_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                # Bind the queue to listen for the specific project deletion event.
                routing_key = 'project.deletion.initiated'
                channel.queue_bind(exchange='project_events', queue=queue_name, routing_key=routing_key)

                self.stdout.write(self.style.SUCCESS('\n [*] Worker is now waiting for project deletion messages.'))
                channel.basic_consume(queue=queue_name, on_message_callback=self.callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError as e:
                self.stderr.write(self.style.ERROR(f'Connection to RabbitMQ failed: {e}. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\nWorker stopped by user.'))
                break

    def callback(self, ch, method, properties, body):
        logger.info("Received a message from the queue.")
        try:
            payload = json.loads(body)
            project_id = payload.get('project_id')

            if project_id:
                # Call the main handler function with the project_id.
                handle_project_cleanup(project_id)
            else:
                logger.warning(f"Received message without a project_id. Discarding: {body}")
        
        except json.JSONDecodeError:
            logger.error(f"Could not decode message body. Discarding: {body}", exc_info=True)
        except Exception as e:
            logger.error(f"An unexpected error occurred in the callback: {e}", exc_info=True)
            # For robustness, we don't requeue. A critical log is better.
        
        # Acknowledge the message so it's removed from the queue.
        ch.basic_ack(delivery_tag=method.delivery_tag)