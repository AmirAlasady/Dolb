# MS13/lrs/services.py

import os
import docker
import httpx
import requests
import json
import redis
import uuid
import time
import logging
from huggingface_hub import HfApi
from django.conf import settings
from rest_framework.exceptions import ValidationError, NotFound

# Import the exception class from the docker library
from docker.errors import DockerException

from .models import LocalModel, ModelInstance
from messaging.event_publisher import lrs_event_publisher

# Get a logger instance for this module
logger = logging.getLogger(__name__)


class LrsService:
    def __init__(self):
        try:
            self.docker_client = docker.from_env()
            self.docker_client.ping() # Check connection
        except DockerException:
            logger.critical("FATAL: Could not connect to the Docker daemon. Is Docker running?")
            raise
            
        self.hf_api = HfApi()
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    def search_huggingface(self, query: str):
        """Searches the HF Hub and annotates results with local status."""
        local_models = {lm.huggingface_id: lm.status for lm in LocalModel.objects.all()}
        results = self.hf_api.list_models(search=query, sort='downloads', direction=-1, limit=50)
        
        annotated_results = []
        for model in results:
            annotated_results.append({
                "id": model.id,
                "pipeline_tag": model.pipeline_tag,
                "downloads": model.downloads,
                "likes": model.likes,
                "local_status": local_models.get(model.id, 'not_installed')
            })
        return annotated_results

    def initiate_model_download(self, huggingface_id: str):
        """Creates a LocalModel record and publishes a download request."""
        if LocalModel.objects.filter(huggingface_id=huggingface_id).exists():
            raise ValidationError("This model has already been registered.")
        try:
            self.hf_api.model_info(huggingface_id)
        except Exception:
            raise NotFound(f"Could not find model '{huggingface_id}' on Hugging Face Hub.")
            
        local_model = LocalModel.objects.create(
            huggingface_id=huggingface_id, status=LocalModel.Status.DOWNLOADING
        )
        lrs_event_publisher.publish_download_requested(
            model_id=str(local_model.id), huggingface_id=huggingface_id
        )
        return local_model
    def deploy_model(self, model_id: uuid.UUID, num_instances: int = 1):
        """
        The ULTIMATE deploy method. Deploys any TGI-compatible model by
        dynamically fetching its configuration from the MS3 internal API.
        """
        try:
            local_model = LocalModel.objects.get(id=model_id, status=LocalModel.Status.DOWNLOADED)
        except LocalModel.DoesNotExist:
            raise NotFound("Model not found or is not in a 'downloaded' state.")

        # --- DYNAMIC CONFIGURATION VIA INTERNAL API ---
        tgi_args_from_config = []
        try:
            ms3_url = settings.MODEL_SERVICE_URL
            if not ms3_url:
                raise ValueError("MODEL_SERVICE_URL is not set in the .env file.")

            # 1. This is the CORRECT endpoint based on your urls.py change.
            endpoint = f"{ms3_url}/ms3/internal/v1/blueprint/"
            params = {
                "provider": "lrs",
                "model_name": local_model.huggingface_id
            }
            
            logger.info(f"Contacting MS3 at {endpoint} to get blueprint for model '{local_model.huggingface_id}'...")
            
            with httpx.Client() as client:
                response = client.get(endpoint, params=params)
                response.raise_for_status() # Raise an exception for 4xx/5xx errors
                blueprint = response.json()

            deployment_config = blueprint.get("deployment_config", {})
            tgi_args_from_config = deployment_config.get("tgi_arguments", [])
            logger.info(f"Successfully fetched deployment config from MS3 with args: {tgi_args_from_config}")

        except httpx.HTTPStatusError as e:
             raise RuntimeError(f"Could not fetch deployment configuration from MS3. MS3 responded with status {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Could not fetch deployment configuration from MS3 for model {local_model.huggingface_id}. Error: {e}")
        # --- END DYNAMIC CONFIGURATION ---


        instances = []
        for i in range(num_instances):
            container_name = f"lrs-instance-{local_model.id.hex[:8]}-{uuid.uuid4().hex[:6]}"
            model_path_in_container = f"{settings.MODEL_MOUNT_PATH}/{local_model.huggingface_id}"
            volumes = { settings.MODEL_STORAGE_PATH: {'bind': settings.MODEL_MOUNT_PATH, 'mode': 'ro'} }
            
            # Build the command dynamically from the fetched config
            command = [
                f"--model-id={model_path_in_container}",
                "--port=80",
                "--sharded=false",
                "--disable-custom-kernels",
            ]
            command.extend(tgi_args_from_config)
            
            environment = {}
            hf_token = os.getenv('HUGGING_FACE_HUB_TOKEN')
            if hf_token: environment['HUGGING_FACE_HUB_TOKEN'] = hf_token

            container = None
            try:
                logger.info(f"Attempting to start container '{container_name}' with final command: {' '.join(command)}")
                container = self.docker_client.containers.run(
                    "ghcr.io/huggingface/text-generation-inference:latest",
                    command=command,
                    detach=True,
                    name=container_name,
                    volumes=volumes,
                    environment=environment,
                    shm_size="2g",
                    device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
                    remove=False,
                    ports={'80/tcp': None}
                )
                
                logger.info(f"Container {container.short_id} created. Waiting for it to become healthy...")
                
                # Get the publicly mapped health check URL
                container.reload()
                port_bindings = container.attrs['NetworkSettings']['Ports'].get('80/tcp')
                if not port_bindings: raise RuntimeError("Container started but has no port bindings.")
                host_port = port_bindings[0]['HostPort']
                health_check_url = f"http://localhost:{host_port}"

                # Robust health check loop
                for _ in range(300): # Poll for up to 2 minutes
                    try:
                        response = requests.get(f"{health_check_url}/health", timeout=1)
                        if response.status_code == 200:
                            logger.info(f"Container {container.short_id} is now HEALTHY.")
                            break
                    except requests.RequestException:
                        pass # It's okay if it fails to connect at first, the server is still starting
                    
                    container.reload()
                    if container.status == 'exited':
                        logs = container.logs().decode('utf-8', 'ignore')
                        logger.error(f"Container {container.short_id} EXITED UNEXPECTEDLY. Logs:\n{logs}")
                        container.remove() # Clean up the failed container
                        raise RuntimeError(f"Container failed to start. Error: {logs[:500]}")
                    
                    time.sleep(2)
                else: # This runs if the loop finishes without a 'break'
                    logs = container.logs().decode('utf-8', 'ignore')
                    container.stop()
                    container.remove()
                    raise RuntimeError(f"Container did not become healthy in time. Last logs:\n{logs}")

                # Get internal IP for the gateway
                internal_ip_address = container.attrs['NetworkSettings']['IPAddress']
                if not internal_ip_address:
                     networks = container.attrs['NetworkSettings']['Networks']
                     first_network = next(iter(networks))
                     internal_ip_address = networks[first_network]['IPAddress']

                # Create the database record for the running instance
                instance = ModelInstance.objects.create(
                    local_model=local_model,
                    container_id=container.id,
                    internal_endpoint=f"http://{internal_ip_address}:80",
                    health_check_url=health_check_url,
                    status=ModelInstance.Status.HEALTHY
                )
                instances.append(instance)

            except Exception as e:
                logger.error(f"An unexpected error occurred while starting instance {i+1}", exc_info=True)
                if container:
                    try: 
                        container.remove(force=True)
                    except: 
                        pass
                raise e

        local_model.status = LocalModel.Status.ACTIVE
        local_model.save()
        
        self._update_downstream_services(local_model)
        
        return instances

    def stop_model(self, model_id: uuid.UUID):
        """Stops and removes all running containers for a given model."""
        try:
            local_model = LocalModel.objects.get(id=model_id)
        except LocalModel.DoesNotExist:
            raise NotFound("Model not found.")
            
        instances = local_model.instances.all()
        for instance in instances:
            try:
                container = self.docker_client.containers.get(instance.container_id)
                logger.warning(f"Stopping and removing container {container.short_id}...")
                container.stop()
                container.remove(force=True)
            except docker.errors.NotFound:
                logger.warning(f"Container {instance.container_id} already gone.")
            except Exception as e:
                logger.error(f"Error stopping container {instance.container_id}: {e}")
            instance.delete()

        local_model.status = LocalModel.Status.DOWNLOADED if local_model.local_path else LocalModel.Status.NOT_INSTALLED
        local_model.save()
        
        self._update_downstream_services(local_model, is_active=False)

    def _update_downstream_services(self, local_model: LocalModel, is_active: bool = True):
        """
        Updates MS3 and the Redis cache for the gateway with the CORRECT endpoint.
        """
        # ... (MS3 update logic is unchanged)

        redis_key = f"lrs:model:{local_model.huggingface_id}"
        
        # --- THIS IS THE FIX ---
        if is_active:
            # Get the HEALTH_CHECK_URL (e.g., http://localhost:49153) for all healthy instances.
            # This is the URL the Gateway needs to use.
            endpoints = list(local_model.instances.filter(status=ModelInstance.Status.HEALTHY).values_list('health_check_url', flat=True))
            
            if endpoints:
                logger.info(f"Updating Redis for {local_model.huggingface_id} with PUBLIC endpoints: {endpoints}")
                # Use a pipeline to atomically delete the old key and add the new members
                pipe = self.redis_client.pipeline()
                pipe.delete(redis_key)
                pipe.sadd(redis_key, *endpoints)
                pipe.execute()
            else:
                 logger.warning(f"Model {local_model.huggingface_id} is active but no healthy instances found. Clearing Redis.")
                 self.redis_client.delete(redis_key)
        else:
            logger.info(f"Model {local_model.huggingface_id} is inactive. Deleting key from Redis.")
            self.redis_client.delete(redis_key)