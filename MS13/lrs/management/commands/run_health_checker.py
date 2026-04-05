# MS13/lrs/management/commands/run_health_checker.py

import time
import docker
import requests
import redis
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from lrs.models import ModelInstance, LocalModel

# Configure logging specifically for this command
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the LRS Health Checker to monitor running model instances.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("--- LRS Health Checker ---"))
        
        try:
            docker_client = docker.from_env()
            docker_client.ping()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"FATAL: Could not connect to Docker. Is it running? Error: {e}"))
            return

        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        
        while True:
            self.stdout.write("Running health check cycle...")
            
            # Check instances that are supposed to be running or are in the process of starting
            instances_to_check = ModelInstance.objects.exclude(status=ModelInstance.Status.STOPPING)
            
            for instance in instances_to_check:
                is_healthy = False
                error_reason = "Unknown"
                try:
                    # 1. Check if the container exists and is running in Docker
                    container = docker_client.containers.get(instance.container_id)
                    if container.status != 'running':
                        raise docker.errors.NotFound(f"Container status is '{container.status}', not 'running'.")
                    
                    # 2. Check if the TGI health endpoint is responsive
                    health_url = f"{instance.health_check_url}/health"
                    response = requests.get(health_url, timeout=3)
                    response.raise_for_status() # Will raise an exception for 4xx/5xx errors
                    
                    is_healthy = True # If we reach here, both checks passed

                except (docker.errors.NotFound, requests.RequestException) as e:
                    error_reason = str(e)
                    is_healthy = False
                except Exception as e:
                    # Generic catch-all to prevent the whole checker from crashing
                    error_reason = f"An unexpected error occurred: {e}"
                    is_healthy = False

                # Now, update the state based on the health check result
                if is_healthy:
                    if instance.status != ModelInstance.Status.HEALTHY:
                        instance.status = ModelInstance.Status.HEALTHY
                        instance.save()
                        redis_client.sadd(f"lrs:model:{instance.local_model.huggingface_id}", instance.internal_endpoint)
                        self.stdout.write(self.style.SUCCESS(f"Instance {str(instance.id)[:8]} is now HEALTHY."))
                else: # Not healthy
                    if instance.status != ModelInstance.Status.UNHEALTHY:
                        self.stderr.write(self.style.ERROR(f"Instance {str(instance.id)[:8]} is now UNHEALTHY. Reason: {error_reason}"))
                        instance.status = ModelInstance.Status.UNHEALTHY
                        instance.save()
                        redis_client.srem(f"lrs:model:{instance.local_model.huggingface_id}", instance.internal_endpoint)

            # Prune parent models: if a model is 'ACTIVE' but has no healthy instances, mark it as 'DOWNLOADED'
            active_models = LocalModel.objects.filter(status=LocalModel.Status.ACTIVE)
            for model in active_models:
                if not model.instances.filter(status=ModelInstance.Status.HEALTHY).exists():
                    self.stdout.write(self.style.WARNING(f"Model '{model.huggingface_id}' is ACTIVE but has no healthy instances. Reverting status to DOWNLOADED."))
                    model.status = LocalModel.Status.DOWNLOADED
                    model.save()
                    redis_client.delete(f"lrs:model:{model.huggingface_id}")

            time.sleep(30) # Wait before the next cycle