# MS11/rag_control_plane/models.py

import uuid
from django.db import models

class KnowledgeCollection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    owner_id = models.UUIDField(db_index=True)
    project_id = models.UUIDField(db_index=True)
    
    strategy_type = models.CharField(max_length=100, default='vector_db')
    config = models.JSONField(default=dict)
    
    # This is the technical name used by the vector store
    vector_store_collection_name = models.CharField(max_length=255, unique=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Generate the unique vector store name only if it's not already set.
        if not self.vector_store_collection_name:
            # Create a unique, URL-safe name for the ChromaDB collection
            self.vector_store_collection_name = f"coll_{str(self.id).replace('-', '')}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class FileCollectionLink(models.Model):
    class IngestionStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        INGESTING = 'ingesting', 'Ingesting'
        COMPLETED = 'completed', 'Completed'
        ERROR = 'error', 'Error'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(KnowledgeCollection, on_delete=models.CASCADE, related_name="linked_files")
    file_id = models.UUIDField()
    status = models.CharField(max_length=20, choices=IngestionStatus.choices, default=IngestionStatus.PENDING)
    
    class Meta:
        # Ensures a file can only be linked to a collection once.
        unique_together = ('collection', 'file_id')

    def __str__(self):
        return f"File {self.file_id} in Collection {self.collection.name} - {self.status}"