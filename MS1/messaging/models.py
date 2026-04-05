import uuid
from django.db import models

class UserSaga(models.Model):
    class SagaStatus(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True, unique=True) # The user being deleted
    status = models.CharField(max_length=50, choices=SagaStatus.choices, default=SagaStatus.IN_PROGRESS)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class UserSagaStep(models.Model):
    class StepStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    saga = models.ForeignKey(UserSaga, on_delete=models.CASCADE, related_name="steps")
    service_name = models.CharField(max_length=100)
    status = models.CharField(max_length=50, choices=StepStatus.choices, default=StepStatus.PENDING)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('saga', 'service_name')