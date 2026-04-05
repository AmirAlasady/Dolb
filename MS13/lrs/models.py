# MS13/lrs/models.py
import uuid
from django.db import models

class LocalModel(models.Model):
    class Status(models.TextChoices):
        NOT_INSTALLED = 'not_installed', 'Not Installed'
        DOWNLOADING = 'downloading', 'Downloading'
        DOWNLOADED = 'downloaded', 'Downloaded'
        ERROR = 'error', 'Error'
        ACTIVE = 'active', 'Active' # At least one instance is running

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    huggingface_id = models.CharField(max_length=255, unique=True, help_text="e.g., 'meta-llama/Llama-2-7b-chat-hf'")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_INSTALLED)
    local_path = models.CharField(max_length=1024, blank=True, null=True, help_text="Absolute path to the model files on the host machine.")
    capabilities = models.JSONField(default=list, help_text="Capabilities inferred from the model config, e.g., ['text', 'tool_use']")
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.huggingface_id

class ModelInstance(models.Model):
    class Status(models.TextChoices):
        STARTING = 'starting', 'Starting'
        HEALTHY = 'healthy', 'Healthy'
        UNHEALTHY = 'unhealthy', 'Unhealthy'
        STOPPING = 'stopping', 'Stopping'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    local_model = models.ForeignKey(LocalModel, on_delete=models.CASCADE, related_name='instances')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTING)
    container_id = models.CharField(max_length=255, unique=True)
    internal_endpoint = models.CharField(max_length=255, help_text="Internal Docker IP and port, e.g., 'http://172.17.0.5:80'")
    gpu_uuid = models.CharField(max_length=255, blank=True, null=True, help_text="UUID of the assigned GPU, if any.")
    last_health_check = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    health_check_url = models.CharField(max_length=255, help_text="Publicly mapped URL for the health checker, e.g., http://localhost:12345", blank=True, null=True)

    def __str__(self):
        # Convert the UUID to its hexadecimal string representation before slicing.
        return f"Instance {self.id.hex[:8]} for {self.local_model.huggingface_id}"
