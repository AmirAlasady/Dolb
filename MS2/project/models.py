from django.db import models
import uuid


class ProjectStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    PENDING_DELETION = 'pending_deletion', 'Pending Deletion'

# Create your models here.
class Project(models.Model):


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # <<< ADD THIS FIELD
    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.ACTIVE,
        db_index=True,
        help_text="The current status of the project (e.g., active, pending deletion)."
    )

    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        help_text="The user-defined name of the project."
    )
    

    owner_id = models.UUIDField(
        db_index=True,
        help_text="The UUID of the user who owns this project. Corresponds to the User ID in the Auth service."
    )


    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        help_text="Timestamp when the project was created."
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the project was last updated."
    )


    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional flexible metadata for the project (e.g., labels, settings)."
    )

    class Meta:

        ordering = ['-created_at']
        
        verbose_name = "Project"
        verbose_name_plural = "Projects"

    def __str__(self):
        """
        Provides a human-readable representation of the object, which is
        useful in the Django admin site and for debugging.
        """
        return f"{self.name} (ID: {self.id})"