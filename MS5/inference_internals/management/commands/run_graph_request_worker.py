import pika
import json
import logging
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from inference_engine.services import InferenceOrchestrationService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS5-GraphWorker - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Listens for Graph Execution requests from MS15.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL
        service = InferenceOrchestrationService()

        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()

                # Declare the exchange and queue to ensure they exist
                channel.exchange_declare(exchange='inference_exchange', exchange_type='topic', durable=True)
                
                # IMPORTANT: This must match what MS15 publishes to
                queue_name = 'inference_request_queue' 
                channel.queue_declare(queue=queue_name, durable=True)
                
                # MS15 publishes with routing key 'inference.request'
                channel.queue_bind(exchange='inference_exchange', queue=queue_name, routing_key='inference.request')

                logger.info(' [*] MS5 Graph Worker waiting for MS15 requests.')

                def callback(ch, method, properties, body):
                    try:
                        payload = json.loads(body)
                        service.process_graph_request(payload)
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON: {body}")
                        ch.basic_ack(delivery_tag=method.delivery_tag) # Discard bad data
                    except Exception as e:
                        logger.error(f"Error processing graph request: {e}", exc_info=True)
                        # Decide on NACK vs ACK based on error type. 
                        # For now, ACK to prevent infinite loops on bad logic.
                        ch.basic_ack(delivery_tag=method.delivery_tag)

                channel.basic_consume(queue=queue_name, on_message_callback=callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection failed: {e}. Retrying in 5s...")
                time.sleep(5)
            except KeyboardInterrupt:
                logger.info("Worker stopped.")
                break