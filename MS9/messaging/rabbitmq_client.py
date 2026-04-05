# messaging/rabbitmq_client.py (Definitive Universal Version)

import pika
import json
import threading
import time
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class RabbitMQClient:
    _thread_local = threading.local()

    def __init__(self, max_retries=3, retry_delay=2):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _get_connection(self):
        connection = getattr(self._thread_local, 'connection', None)
        if connection is None or connection.is_closed:
            logger.info(f"Thread {threading.get_ident()}: No active RabbitMQ connection. Creating new one...")
            try:
                params = pika.URLParameters(settings.RABBITMQ_URL)
                self._thread_local.connection = pika.BlockingConnection(params)
                logger.info(f"Thread {threading.get_ident()}: Connection successful.")
            except pika.exceptions.AMQPConnectionError as e:
                logger.critical(f"Thread {threading.get_ident()} failed to connect to RabbitMQ: {e}", exc_info=True)
                raise
        return self._thread_local.connection

    def _invalidate_connection(self):
        """
        Safely closes and removes the connection for the current thread.
        This version is resilient to the connection already being closed.
        """
        connection = getattr(self._thread_local, 'connection', None)
        if connection is not None:
            try:
                if connection.is_open:
                    connection.close()
                    logger.warning(f"Thread {threading.get_ident()}: Invalidated and closed RabbitMQ connection.")
            except (pika.exceptions.AMQPError, OSError, AttributeError) as e:
                # Log the error but proceed, as our goal is just to ensure it's gone.
                logger.warning(f"Thread {threading.get_ident()}: Error while closing stale connection (this is often safe to ignore): {e}")
            finally:
                # Ensure the attribute is removed regardless of success or failure.
                del self._thread_local.connection

    def publish(self, exchange_name, routing_key, body, exchange_type='topic'):
        attempt = 0
        while attempt < self.max_retries:
            try:
                connection = self._get_connection()
                channel = connection.channel() # This can fail if the connection is stale
                
                channel.exchange_declare(
                    exchange=exchange_name, exchange_type=exchange_type, durable=True
                )
                message_body = json.dumps(body, default=str)
                channel.basic_publish(
                    exchange=exchange_name,
                    routing_key=routing_key,
                    body=message_body,
                    properties=pika.BasicProperties(
                        content_type='application/json',
                        delivery_mode=pika.DeliveryMode.Persistent,
                    )
                )
                logger.info(f"Successfully published to exchange '{exchange_name}' with key '{routing_key}'.")
                # Close the channel after publishing
                if channel.is_open:
                    channel.close()
                return

            except (pika.exceptions.AMQPError, OSError) as e:
                logger.warning(f"Publish attempt {attempt + 1} to '{exchange_name}' failed: {e}. Invalidating and retrying...")
                self._invalidate_connection()
                attempt += 1
                if attempt >= self.max_retries:
                    logger.critical(f"Failed to publish message after {self.max_retries} attempts.")
                    raise

rabbitmq_client = RabbitMQClient()