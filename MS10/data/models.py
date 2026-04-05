import uuid
from django.db import models

class StoredFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    owner_id = models.UUIDField(db_index=True)
    project_id = models.UUIDField(db_index=True)
    
    filename = models.CharField(max_length=255)
    mimetype = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField()
    
    storage_path = models.CharField(max_length=1024, help_text="Path/key to the raw file in object storage.")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']