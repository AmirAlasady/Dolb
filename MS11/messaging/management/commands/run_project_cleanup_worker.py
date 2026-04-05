# MS11/messaging/management/commands/run_project_cleanup_worker.py

import pika
import json
import time
import logging
import chromadb
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction

from rag_control_plane.models import KnowledgeCollection
from messaging.event_publisher import rag_event_publisher

# Configure logging specifically for this worker
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS11-CleanupWorker - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    Django management command that runs a RabbitMQ worker. This worker listens for
    `project.deletion.initiated` events and cleans up all associated KnowledgeCollection
    objects, including their data in the ChromaDB vector store.
    """
    help = 'Runs the RAG Service worker for the Project Deletion Saga.'

    def handle_project_cleanup(self, project_id: str):
        """
        The core, idempotent business logic for cleaning up all RAG resources
        associated with a given project_id.
        """
        logger.info(f"--- RAG Cleanup Initiated for project_id: {project_id} ---")
        
        try:
            # Find all KnowledgeCollection metadata records for the project.
            collections_to_delete = KnowledgeCollection.objects.filter(project_id=project_id)
            
            if not collections_to_delete.exists():
                logger.info(f"No RAG collections found for project {project_id}. Cleanup action is complete.")
            else:
                logger.info(f"Found {collections_to_delete.count()} RAG collection(s) to delete for project {project_id}.")
                
                try:
                    # Establish a client connection to the vector store.
                    chroma_client = chromadb.HttpClient(
                        host=settings.CHROMA_DB_HOST, 
                        port=settings.CHROMA_DB_PORT
                    )
                    
                    # First, delete the collections from the external vector store.
                    for collection in collections_to_delete:
                        try:
                            logger.warning(f"Deleting vector store collection '{collection.vector_store_collection_name}' from ChromaDB.")
                            chroma_client.delete_collection(name=collection.vector_store_collection_name)
                        except Exception as e:
                            # Gracefully handle if collection is already gone. This is not a critical failure.
                            logger.warning(f"Could not delete ChromaDB collection '{collection.vector_store_collection_name}', it may have already been deleted. Details: {e}")
                        # --- END OF FIX ---
                    # After attempting to clean the vector store, delete the database records.
                    # This is done in a single, efficient bulk delete operation.
                    with transaction.atomic():
                        deleted_count, _ = collections_to_delete.delete()
                    logger.info(f"Successfully deleted {deleted_count} KnowledgeCollection records from the database.")

                except Exception as e:
                    logger.critical(f"A critical error occurred during the cleanup process for project {project_id}", exc_info=True)
                    # On critical failure (e.g., can't connect to Chroma), we must not send a success confirmation.
                    return # Exit the function early.
            
            # After successful cleanup (or if there was nothing to clean), publish the confirmation event.
            rag_event_publisher.publish_project_cleanup_confirmation(project_id)
            logger.info(f"--- RAG Cleanup Finished for project_id: {project_id} ---")

        except Exception as e:
            logger.critical(f"An unexpected top-level error occurred during cleanup for project {project_id}: {e}", exc_info=True)
            # Do not publish confirmation on failure.

    def handle(self, *args, **options):
        """The main loop that connects to RabbitMQ and consumes messages."""
        rabbitmq_url = settings.RABBITMQ_URL
        self.stdout.write(self.style.SUCCESS("--- RAG Service Project Cleanup Worker ---"))
        self.stdout.write(f"Connecting to RabbitMQ at {rabbitmq_url}...")
        
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()

                channel.exchange_declare(exchange='project_events', exchange_type='topic', durable=True)
                
                queue_name = 'rag_project_cleanup_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                routing_key = 'project.deletion.initiated'
                channel.queue_bind(exchange='project_events', queue=queue_name, routing_key=routing_key)

                self.stdout.write(self.style.SUCCESS('\n [*] Worker is now waiting for project deletion messages.'))
                
                def callback(ch, method, properties, body):
                    try:
                        payload = json.loads(body)
                        project_id = payload.get('project_id')
                        if project_id:
                            self.handle_project_cleanup(project_id)
                        else:
                            logger.warning(f"Received message without a project_id. Discarding: {body}")
                    except Exception as e:
                        logger.error(f"Error in message callback: {e}", exc_info=True)
                    
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                channel.basic_consume(queue=queue_name, on_message_callback=callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError as e:
                self.stderr.write(self.style.ERROR(f'Connection to RabbitMQ failed: {e}. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\nWorker stopped by user.'))
                break