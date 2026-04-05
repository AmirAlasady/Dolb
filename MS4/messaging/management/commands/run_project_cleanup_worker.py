# MS4/messaging/management/commands/run_project_cleanup_worker.py

import pika
import json
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from nodes.models import Node
from messaging.event_publisher import node_event_publisher # <-- USE THE STANDARD PUBLISHER

def handle_project_deletion(project_id: str):
    """
    The core business logic for cleaning up nodes. This is idempotent.
    """
    print(f" [!] Received request to delete nodes for project: {project_id}")
    
    nodes_deleted, _ = Node.objects.filter(project_id=project_id).delete()
    
    print(f" [✓] Deleted {nodes_deleted} nodes for project {project_id}.")
    
    # After successful deletion, publish the confirmation event using the standard client.
    node_event_publisher.publish_nodes_for_project_deleted(project_id)


class Command(BaseCommand):
    help = 'Runs a RabbitMQ worker to listen for project deletion events.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()
    
                channel.exchange_declare(exchange='project_events', exchange_type='topic', durable=True)
                
                queue_name = 'node_project_cleanup_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                routing_key = 'project.deletion.initiated'
                channel.queue_bind(exchange='project_events', queue=queue_name, routing_key=routing_key)
    
                self.stdout.write(self.style.SUCCESS(' [*] NodeService project cleanup worker waiting for messages.'))
    
                def callback(ch, method, properties, body):
                    try:
                        data = json.loads(body)
                        project_id = data.get('project_id')
        
                        if project_id:
                            handle_project_deletion(project_id)
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f" [!] Error handling project deletion for {project_id}: {e}"))
                        # Nack logic would go here in production
                    
                    ch.basic_ack(delivery_tag=method.delivery_tag)
    
                channel.basic_consume(queue=queue_name, on_message_callback=callback)
                channel.start_consuming()
            except pika.exceptions.AMQPConnectionError:
                self.stderr.write(self.style.ERROR('Connection to RabbitMQ failed. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('Worker stopped.'))
                break