# MS9/messaging/management/commands/run_project_cleanup_worker.py
import pika
import json
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from memory.models import MemoryBucket
from messaging.event_publisher import memory_event_publisher

class Command(BaseCommand):
    help = 'Listens for project deletion events to clean up memory buckets.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()
                channel.exchange_declare(exchange='project_events', exchange_type='topic', durable=True)
                queue_name = 'memory_project_cleanup_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                channel.queue_bind(exchange='project_events', queue=queue_name, routing_key='project.deletion.initiated')
                
                self.stdout.write(self.style.SUCCESS(' [*] Memory project cleanup worker is waiting for messages.'))
                channel.basic_consume(queue=queue_name, on_message_callback=self.callback)
                channel.start_consuming()
            except pika.exceptions.AMQPConnectionError:
                self.stderr.write(self.style.ERROR('Connection to RabbitMQ failed. Retrying...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('Worker stopped.'))
                break

    def callback(self, ch, method, properties, body):
        try:
            payload = json.loads(body)
            project_id = payload.get('project_id')
            if project_id:
                deleted_count, _ = MemoryBucket.objects.filter(project_id=project_id).delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} memory buckets for project {project_id}."))
                
                # Publish confirmation back to the project saga
                memory_event_publisher.publish_project_cleanup_confirmation(project_id)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error during project cleanup: {e}"))
            # In production, nack and DLQ
        
        ch.basic_ack(delivery_tag=method.delivery_tag)