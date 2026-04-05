# MS14/messaging/management/commands/run_project_event_consumer.py

import pika
import json
import time
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from graphcontrol.services.graph_service import GraphService
from graphcontrol.services.security import RequestContext
from messaging.event_publisher import graph_event_publisher

logger = logging.getLogger(__name__)

def handle_project_deletion(project_id: str):
    """
    Deletes all graphs associated with the given project_id.
    """
    logger.info(f" [!] Received request to delete graphs for project: {project_id}")
    
    # We use a system context (no user token) because this is a background worker task.
    # The delete_graphs_for_project method has been updated to handle this (skips unclaiming).
    ctx = RequestContext(jwt_token=None)
    service = GraphService()
    
    try:
        count, _ = service.delete_graphs_for_project(ctx, project_id)
        logger.info(f" [✓] Deleted {count} graphs for project {project_id}.")
        
        # Publish confirmation to MS2
        graph_event_publisher.publish_graphs_for_project_deleted(project_id)
        
    except Exception as e:
        logger.error(f"Error deleting graphs for project {project_id}: {e}")

class Command(BaseCommand):
    help = 'Runs a RabbitMQ worker to listen for project deletion events.'

    def handle(self, *args, **options):
        # Fallback to localhost if not set (matches other services)
        rabbitmq_url = getattr(settings, 'RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        
        reconnect_delay = 5

        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()
    
                # Declare the exchange (idempotent)
                channel.exchange_declare(exchange='project_events', exchange_type='topic', durable=True)
                
                # Declare a queue for MS14 to listen to these events
                queue_name = 'ms14_project_cleanup_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                # Bind the queue to the exchange
                routing_key = 'project.deletion.initiated'
                channel.queue_bind(exchange='project_events', queue=queue_name, routing_key=routing_key)
    
                self.stdout.write(self.style.SUCCESS(f' [*] MS14 Project Cleanup Worker waiting for messages in {queue_name}.'))
    
                def callback(ch, method, properties, body):
                    try:
                        data = json.loads(body)
                        project_id = data.get('project_id')
                        
                        if project_id:
                            handle_project_deletion(project_id)
                        else:
                            logger.warning("Received project deletion event without project_id")
                            
                    except Exception as e:
                        logger.error(f" [!] Error handling project deletion event: {e}")
                        # In a real system, we might nack or dead-letter, but here we ack to avoid loops
                    
                    ch.basic_ack(delivery_tag=method.delivery_tag)
    
                channel.basic_consume(queue=queue_name, on_message_callback=callback)
                channel.start_consuming()
                
            except pika.exceptions.AMQPConnectionError:
                self.stderr.write(self.style.ERROR(f'Connection to RabbitMQ failed. Retrying in {reconnect_delay} seconds...'))
                time.sleep(reconnect_delay)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('Worker stopped.'))
                break
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Unexpected error: {e}. Retrying in {reconnect_delay} seconds...'))
                time.sleep(reconnect_delay)
