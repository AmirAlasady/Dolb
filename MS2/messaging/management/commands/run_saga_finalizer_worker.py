# messaging/management/commands/run_saga_finalizer_worker.py

import pika
import json
import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
# --- FIX IS HERE ---
# Use an absolute import path from the top-level app name.
# Django knows where to find the 'projects' and 'messaging' apps.
from project.models import Project 
from messaging.models import Saga, SagaStep

class Command(BaseCommand):
    help = 'Runs a RabbitMQ worker to listen for saga confirmation events.'

    def handle(self, *args, **options):
        # In production, you would use a variable from settings.py for the RabbitMQ URL
        # For simplicity, we hardcode it here.
        rabbitmq_url = settings.RABBITMQ_URL

        while True:
            try:
                self.stdout.write('Connecting to RabbitMQ...')
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()

                # Declare the exchange and a durable queue for this worker
                channel.exchange_declare(exchange='project_events', exchange_type='topic', durable=True)
                queue_name = 'project_finalizer_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                # We listen for confirmation events.
                # routing_key format: resource.<resource_name>.<action>
                # The '#' wildcard listens for all events published to this exchange.
                # A more specific key would be 'resource.for_project.deleted.*'
                routing_key = 'resource.for_project.deleted.*'
                channel.queue_bind(exchange='project_events', queue=queue_name, routing_key=routing_key)

                self.stdout.write(self.style.SUCCESS(' [*] Waiting for confirmation messages. To exit press CTRL+C'))

                def callback(ch, method, properties, body):
                    try:
                        data = json.loads(body)
                        project_id = data.get('project_id')
                        service_name = data.get('service_name')

                        if not project_id or not service_name:
                            self.stderr.write(self.style.WARNING(f" [!] Received malformed message, discarding: {body}"))
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            return

                        self.stdout.write(f" [x] Received confirmation from '{service_name}' for project '{project_id}'")

                        with transaction.atomic():
                            # Find the relevant saga. Use select_for_update to lock the row.
                            try:
                                saga = Saga.objects.select_for_update().get(
                                    related_resource_id=project_id,
                                    status=Saga.SagaStatus.IN_PROGRESS
                                )
                            except Saga.DoesNotExist:
                                self.stderr.write(self.style.WARNING(f" [!] Warning: Received confirmation for an unknown or completed saga. Project ID: {project_id}"))
                                ch.basic_ack(delivery_tag=method.delivery_tag)
                                return

                            # Mark the specific step as completed
                            step, created = SagaStep.objects.select_for_update().get_or_create(
                                saga=saga, 
                                service_name=service_name,
                                defaults={'status': SagaStep.StepStatus.COMPLETED}
                            )
                            if not created and step.status != SagaStep.StepStatus.COMPLETED:
                                step.status = SagaStep.StepStatus.COMPLETED
                                step.save()

                            # Check if all steps for this saga are now complete
                            all_steps_completed = not saga.steps.filter(status=SagaStep.StepStatus.PENDING).exists()
                            
                            if all_steps_completed:
                                self.stdout.write(self.style.SUCCESS(f" [!] All steps for saga {saga.id} complete. Finalizing project deletion."))
                                
                                # All confirmations received, perform the hard delete
                                Project.objects.filter(id=project_id).delete()
                                
                                # Mark the saga as complete
                                saga.status = Saga.SagaStatus.COMPLETED
                                saga.save()
                                self.stdout.write(self.style.SUCCESS(f" [!] Project {project_id} deleted and saga completed."))

                    except json.JSONDecodeError:
                        self.stderr.write(self.style.ERROR(f" [!] Could not decode message body: {body}"))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f" [!] An unexpected error occurred: {e}"))
                        # In a production system, you might 'nack' the message to requeue it
                        # or route it to a Dead Letter Queue (DLQ). For now, we'll ack to prevent loops.

                    # Acknowledge the message so RabbitMQ knows it has been processed.
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                channel.basic_consume(queue=queue_name, on_message_callback=callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError:
                self.stderr.write(self.style.ERROR('Connection to RabbitMQ failed. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS('Worker stopped by user.'))
                break