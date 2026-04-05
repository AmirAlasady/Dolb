import uuid
from django.db import models

class MemoryBucket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    
    # Ownership and Scoping
    owner_id = models.UUIDField(db_index=True, help_text="The user who owns this bucket.")
    project_id = models.UUIDField(db_index=True, help_text="The project this bucket belongs to.")
    
    # Logic Configuration
    memory_type = models.CharField(max_length=100, default='conversation_buffer_window')
    config = models.JSONField(default=dict, help_text="Type-specific config, e.g., {'k': 10}")
    
    # Calculated Metadata
    message_count = models.PositiveIntegerField(default=0)
    token_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bucket = models.ForeignKey(MemoryBucket, on_delete=models.CASCADE, related_name='messages')
    
    # The rich, multimodal content block
    content = models.JSONField() 
    
    # For idempotency from the Executor's feedback loop
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']