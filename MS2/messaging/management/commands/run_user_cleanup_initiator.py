# project service/messaging/management/commands/run_user_cleanup_initiator.py

import pika
import json
import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from project.models import Project, ProjectStatus
from messaging.models import Saga, SagaStep
from messaging.event_publisher import event_publisher

def initiate_single_project_deletion_saga(project: Project):
    """
    A reusable function that encapsulates the complete logic for starting
    ONE project deletion saga.
    """
    if Saga.objects.filter(related_resource_id=project.id, status=Saga.SagaStatus.IN_PROGRESS).exists():
        print(f" [!] Saga for project {project.id} is already in progress. Skipping initiation.")
        return

    print(f"   -> Initiating deletion saga for project: {project.id}")
    try:
        with transaction.atomic():
            project.status = ProjectStatus.PENDING_DELETION
            project.save(update_fields=['status'])

            saga = Saga.objects.create(saga_type='project_deletion', related_resource_id=project.id)
            services_to_confirm = ['NodeService']
            for service_name in services_to_confirm:
                SagaStep.objects.create(saga=saga, service_name=service_name)
            
            event_publisher.publish_project_deletion_initiated(project.id, project.owner_id)
            print(f"   [✓] Successfully initiated saga for project: {project.id}")

    except Exception as e:
        print(f" [!] CRITICAL ERROR: Failed to initiate saga for project {project.id}. Error: {e}")

class Command(BaseCommand):
    help = 'Listens for user deletion events to kick off project deletions.'

    def handle(self, *args, **options):
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
                channel = connection.channel()
                
                channel.exchange_declare(exchange='user_events', exchange_type='topic', durable=True)
                
                queue_name = 'project_user_cleanup_initiator_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                channel.queue_bind(exchange='user_events', queue=queue_name, routing_key='user.deletion.initiated')
                
                self.stdout.write(self.style.SUCCESS(' [*] Project Service user cleanup initiator is waiting for messages.'))
                
                channel.basic_consume(queue=queue_name, on_message_callback=self.callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError as e:
                self.stderr.write(self.style.ERROR(f"Connection error: {e}. Retrying in 5s."))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Worker stopped."))
                break

    def callback(self, ch, method, properties, body):
        try:
            data = json.loads(body)
            user_id = data.get('user_id')
            self.stdout.write(f" [x] Received user.deletion.initiated event for user: {user_id}")
            
            if not user_id:
                self.stderr.write(" [!] Message lacks user_id. Discarding.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            projects_to_delete = Project.objects.filter(owner_id=user_id, status=ProjectStatus.ACTIVE)
            
            if projects_to_delete.exists():
                self.stdout.write(f" [!] Found {projects_to_delete.count()} project(s) to delete for user {user_id}.")
                for project in projects_to_delete:
                    initiate_single_project_deletion_saga(project)
            else:
                 self.stdout.write(f" [!] No active projects found for user {user_id}.")
            
            # --------------------------------------------------------------------
            # >>>>>>>>>>>> THE CRITICAL FIX IS HERE <<<<<<<<<<<<<<<
            # --------------------------------------------------------------------
            # After handling all projects for the user (either by starting their
            # deletion sagas or by finding none), we MUST publish the confirmation
            # event that the Auth Service is waiting for.
            self.stdout.write(f" [✓] Finished processing all projects for user {user_id}. Publishing confirmation.")
            event_publisher.publish_all_projects_for_user_deleted(user_id)
            # --------------------------------------------------------------------

        except Exception as e:
            self.stderr.write(self.style.ERROR(f" [!] Worker callback crashed: {e}"))
        
        ch.basic_ack(delivery_tag=method.delivery_tag)