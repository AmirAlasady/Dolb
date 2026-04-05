# in nodes/models.py

import uuid
from django.db import models


class NodeStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'             # Fully functional
    ALTERED = 'altered', 'Altered'           # A non-critical dependency was removed (e.g., a tool)
    INACTIVE = 'inactive', 'Inactive'
    DRAFT = 'draft', 'Draft'                 # Initial state, not yet configured


class Node(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    

    status = models.CharField(
        max_length=20,
        choices=NodeStatus.choices,
        default=NodeStatus.DRAFT, # <-- Set default to DRAFT
        db_index=True,
        help_text="The current status of the node (e.g., active, altered, inactive)."
    )

    is_used_in_graph = models.BooleanField(
        default=False, 
        help_text="True if this node is currently linked to a GNode in the Graph Control Plane (MS14)."
    )
    
    project_id = models.UUIDField(
        db_index=True,
        help_text="The Project this Node belongs to."
    )
    
    # ------------------ THE ONE AND ONLY FIX IS HERE ------------------
    owner_id = models.UUIDField(
        db_index=True,
        help_text="The UUID of the user who owns this Node. Corresponds to the User UUID in the Auth service JWT."
    )
    # --------------------------------------------------------------------
    
    name = models.CharField(
        max_length=255,
        help_text="The user-defined name for this Node (e.g., 'My Research Agent')."
    )

    configuration = models.JSONField(
        default=dict,
        help_text="The complete configuration blueprint for this node's behavior."
    )

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Node"
        verbose_name_plural = "Nodes"

    def __str__(self):
        return f"{self.name} (Project: {self.project_id})"