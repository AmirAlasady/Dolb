import uuid
from django.db import models


class Saga(models.Model):
    """Tracks the state of a distributed saga."""
    class SagaStatus(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    saga_type = models.CharField(max_length=100, db_index=True) # e.g., 'project_deletion'
    related_resource_id = models.UUIDField(db_index=True) # The ID of the project being deleted
    status = models.CharField(max_length=50, choices=SagaStatus.choices, default=SagaStatus.IN_PROGRESS)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Saga {self.id} ({self.saga_type}) for {self.related_resource_id}"

class SagaStep(models.Model):
    """Tracks the individual confirmation steps for a given saga."""
    class StepStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    saga = models.ForeignKey(Saga, on_delete=models.CASCADE, related_name="steps")
    service_name = models.CharField(max_length=100) # e.g., 'NodeService', 'AIModelService'
    status = models.CharField(max_length=50, choices=StepStatus.choices, default=StepStatus.PENDING)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('saga', 'service_name')

    def __str__(self):
        return f"Step {self.service_name} for Saga {self.saga.id} - {self.status}"