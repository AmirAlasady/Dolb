# auth_service/messaging/management/commands/run_user_saga_finalizer.py

import pika
import json
from django.core.management.base import BaseCommand
from django.db import transaction

# Correctly importing the models defined in accounts/models.py
from accounts.models import User
from messaging.models import UserSaga, UserSagaStep
from django.conf import settings

class Command(BaseCommand):
    help = 'Runs a worker to finalize user deletion sagas.'

    def handle(self, *args, **options):
        connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        channel = connection.channel()

        # Declare exchanges this worker needs to listen to
        channel.exchange_declare(exchange='user_events', exchange_type='topic', durable=True)
        
        queue_name = 'user_finalizer_queue'
        channel.queue_declare(queue=queue_name, durable=True)
        
        # Bind to both types of confirmation events
        channel.queue_bind(exchange='user_events', queue=queue_name, routing_key='resource.for_user.deleted.*')
        channel.queue_bind(exchange='user_events', queue=queue_name, routing_key='all_projects_for_user.deleted')
        
        self.stdout.write(' [*] User Saga Finalizer waiting for messages.')

        def callback(ch, method, properties, body):
            data = json.loads(body)
            routing_key = method.routing_key
            user_id = data.get('user_id')

            service_name = None
            if routing_key.startswith('resource.for_user.deleted.'):
                # e.g., 'resource.for_user.deleted.AIModelService' -> 'AIModelService'
                service_name = routing_key.split('.')[-1]
            elif routing_key == 'all_projects_for_user.deleted':
                service_name = 'ProjectService'

            if not service_name or not user_id:
                self.stderr.write(f" [!] Invalid message received. Key: {routing_key}, Body: {data}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            self.stdout.write(f" [x] Received confirmation from '{service_name}' for user '{user_id}'")

            try:
                with transaction.atomic():
                    # Find the specific saga that is currently in progress for this user
                    saga = UserSaga.objects.select_for_update().get(user_id=user_id, status=UserSaga.SagaStatus.IN_PROGRESS)
                    
                    # Find the corresponding step for the service that just reported back
                    step = saga.steps.select_for_update().get(service_name=service_name)
                    
                    # Idempotency check: If we've already processed this confirmation, do nothing.
                    if step.status == UserSagaStep.StepStatus.COMPLETED: # <--- CORRECTED MODEL NAME
                        self.stdout.write(f" [!] Step for {service_name} already completed. Ignoring duplicate.")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        return

                    # Mark the step as complete
                    step.status = UserSagaStep.StepStatus.COMPLETED # <--- CORRECTED MODEL NAME
                    step.save()

                    # Check if all steps for this saga are now finished
                    if not saga.steps.filter(status=UserSagaStep.StepStatus.PENDING).exists(): # <--- CORRECTED MODEL NAME
                        self.stdout.write(f" [!] All steps for user saga {saga.id} complete. Finalizing user deletion.")
                        
                        # HARD DELETE the user from the database
                        User.objects.filter(id=user_id).delete()
                        
                        # Mark the entire saga as complete
                        saga.status = UserSaga.SagaStatus.COMPLETED
                        saga.save()
                        self.stdout.write(f" [!] User {user_id} deleted and saga completed.")
            
            except UserSaga.DoesNotExist:
                self.stderr.write(f" [!] Warning: Received confirmation for an unknown or completed saga. User ID: {user_id}")
            except UserSagaStep.DoesNotExist: # <--- CORRECTED MODEL NAME
                self.stderr.write(f" [!] Warning: Received confirmation from an unexpected service '{service_name}' for saga on User ID: {user_id}")
            except Exception as e:
                self.stderr.write(f" [!] Error processing message: {e}")
                # In production, you'd add logic here to nack (not acknowledge) the message
                # so it can be retried or sent to a Dead Letter Queue.

            # Acknowledge the message was processed successfully
            ch.basic_ack(delivery_tag=method.delivery_tag)

        channel.basic_consume(queue=queue_name, on_message_callback=callback)
        channel.start_consuming()