import pika
import json
import time
from django.core.management.base import BaseCommand
from django.conf import settings

from tools.models import Tool
from messaging.event_publisher import tool_event_publisher

class Command(BaseCommand):
    help = 'Runs a RabbitMQ worker to clean up user-owned tools upon account deletion.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()
                channel.exchange_declare(exchange='user_events', exchange_type='topic', durable=True)
                
                queue_name = 'tool_user_cleanup_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                routing_key = 'user.deletion.initiated'
                channel.queue_bind(exchange='user_events', queue=queue_name, routing_key=routing_key)

                self.stdout.write(self.style.SUCCESS(' [*] Tool service cleanup worker waiting for messages.'))
                channel.basic_consume(queue=queue_name, on_message_callback=self.callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError:
                self.stderr.write(self.style.ERROR('Connection to RabbitMQ failed. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('Worker stopped.'))
                break

    def callback(self, ch, method, properties, body):
        try:
            data = json.loads(body)
            user_id = data.get('user_id')

            if user_id:
                self.stdout.write(f" [x] Received request to delete tools for user: {user_id}")
                deleted_count, _ = Tool.objects.filter(owner_id=user_id, is_system_tool=False).delete()
                self.stdout.write(self.style.SUCCESS(f" [✓] Deleted {deleted_count} tools for user {user_id}."))
                
                # IMPORTANT: Publish confirmation that this service has completed its part of the saga.
                tool_event_publisher.publish_resource_for_user_deleted(user_id)
            else:
                self.stderr.write(" [!] Message received without user_id. Discarding.")
        
        except Exception as e:
            self.stderr.write(self.style.ERROR(f" [!] An error occurred during tool cleanup: {e}"))
            # In production, you would 'nack' the message and send to a DLQ.
        
        ch.basic_ack(delivery_tag=method.delivery_tag)