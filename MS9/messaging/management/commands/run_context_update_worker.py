# MS9/messaging/management/commands/run_context_update_worker.py

import pika
import json
import time
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction, IntegrityError
from memory.models import Message, MemoryBucket

# Configure logging for this worker
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS9-UpdateWorker - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Listens for memory context updates from the Inference Executor.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL
        self.stdout.write(self.style.SUCCESS("--- Memory Context Update Worker ---"))
        self.stdout.write(f"Connecting to RabbitMQ at {rabbitmq_url}...")
        
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()

                exchange_name = 'memory_exchange'
                self.stdout.write(f"Declaring exchange: '{exchange_name}' (type=topic, durable=True)")
                channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
                
                queue_name = 'memory_context_update_queue'
                self.stdout.write(f"Declaring queue: '{queue_name}' (durable=True)")
                channel.queue_declare(queue=queue_name, durable=True)
                
                routing_key = 'memory.context.update'
                self.stdout.write(f"Binding queue '{queue_name}' to exchange '{exchange_name}' with key '{routing_key}'")
                channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=routing_key)
                
                self.stdout.write(self.style.SUCCESS('\n [*] Worker is now waiting for memory update messages.'))
                channel.basic_consume(queue=queue_name, on_message_callback=self.callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError as e:
                self.stderr.write(self.style.ERROR(f'Connection to RabbitMQ failed: {e}. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\nWorker stopped by user.'))
                break

    def callback(self, ch, method, properties, body):
        logger.info(f"\n--- Context Update Event Received ---")
        try:
            payload = json.loads(body)
            idempotency_key = payload.get("idempotency_key")
            bucket_id = payload.get("memory_bucket_id")
            
            logger.info(f"    Job ID (Idempotency Key): {idempotency_key}")
            logger.info(f"    Target Bucket ID: {bucket_id}")

            if not idempotency_key or not bucket_id:
                logger.error("Message missing key data. Discarding.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            try:
                with transaction.atomic():
                    # The idempotency check remains the same.
                    if Message.objects.filter(idempotency_key=idempotency_key).exists():
                        logger.warning(f"    DUPLICATE job '{idempotency_key}' detected in DB. Discarding message.")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        logger.info(f"--- Event Processing Finished ---")
                        return

                    logger.info(f"    New job. Proceeding to update memory.")
                    messages_to_add_raw = payload.get("messages_to_add", [])
                    if not messages_to_add_raw:
                        logger.warning("    Payload contained no messages to add. Nothing to do.")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        logger.info(f"--- Event Processing Finished ---")
                        return

                    bucket = MemoryBucket.objects.get(id=bucket_id)
                    
                    # --- THE DEFINITIVE FIX IS HERE ---
                    messages_to_create = []
                    for i, msg_data in enumerate(messages_to_add_raw):
                        # Apply the idempotency key ONLY to the first message in the batch.
                        # All subsequent messages for the same job will have a null key.
                        current_key = idempotency_key if i == 0 else None
                        
                        messages_to_create.append(
                            Message(
                                bucket=bucket,
                                content=msg_data,
                                idempotency_key=current_key
                            )
                        )
                    # --- END OF FIX ---
                        
                    Message.objects.bulk_create(messages_to_create)
                    
                    # This logic should be outside the loop
                    bucket.message_count = bucket.messages.count()
                    bucket.save(update_fields=['message_count', 'updated_at'])
                    
                    logger.info(f"    SUCCESS: Added {len(messages_to_create)} messages to bucket {bucket_id}.")

            except MemoryBucket.DoesNotExist:
                logger.error(f"    FAILURE: Memory bucket '{bucket_id}' not found. Cannot save messages.")
            except IntegrityError:
                logger.warning(f"    DUPLICATE job '{idempotency_key}' detected by DB constraint during race condition. Discarding message.")
            
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        
        logger.info(f"--- Event Processing Finished ---")
        ch.basic_ack(delivery_tag=method.delivery_tag)