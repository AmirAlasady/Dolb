import uuid
from django.db import models

class ToolType(models.TextChoices):
    STANDARD = 'standard', 'Standard'
    MCP = 'mcp', 'Model Context Protocol'

class Tool(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Unique, programmatic name, e.g., 'get_current_weather'.")
    is_system_tool = models.BooleanField(default=False, db_index=True)
    owner_id = models.UUIDField(db_index=True, null=True, blank=True, help_text="NULL for system tools.")
    tool_type = models.CharField(max_length=20, choices=ToolType.choices, default=ToolType.STANDARD)
    definition = models.JSONField(help_text="The tool's complete definition, including its schema and execution details.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('owner_id', 'name')
        ordering = ['-is_system_tool', 'name']

    def __str__(self):
        return f"{self.name} ({self.tool_type})"