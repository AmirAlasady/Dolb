# MS7/tools/services.py
import uuid
from django.db.models import Q, QuerySet
from .models import Tool

class ToolService:
    """
    The service layer for handling all business logic related to Tool objects.
    This separates the core logic from the view layer (HTTP request/response handling).
    """

    def get_user_accessible_tools(self, user_id: uuid.UUID) -> QuerySet[Tool]:
        """
        Returns a queryset of all tools that a given user is allowed to see and use.
        This includes all system tools plus the user's own private tools.

        Args:
            user_id: The UUID of the user making the request.

        Returns:
            A Django QuerySet containing the accessible Tool objects.
        """
        return Tool.objects.filter(
            Q(is_system_tool=True) | Q(owner_id=user_id)
        )

    def get_tool_by_id_for_user(self, tool_id: uuid.UUID, user_id: uuid.UUID) -> Tool | None:
        """
        Retrieves a single tool by its ID, but only if the user has permission to access it.
        This prevents one user from accessing another user's private tool via its ID.

        Args:
            tool_id: The UUID of the tool to retrieve.
            user_id: The UUID of the user making the request.

        Returns:
            The Tool object if found and accessible, otherwise None.
        """
        try:
            tool = self.get_user_accessible_tools(user_id).get(id=tool_id)
            return tool
        except Tool.DoesNotExist:
            return None

    def create_user_tool(self, owner_id: uuid.UUID, name: str, tool_type: str, definition: dict) -> Tool:
        """
        Creates a new, private tool for a specific user.

        Args:
            owner_id: The UUID of the user who will own this tool.
            name: The programmatic name of the tool.
            tool_type: The type of the tool (e.g., 'standard').
            definition: The complete JSON definition for the tool.

        Returns:
            The newly created Tool object.
        """
        # The serializer should have already validated the data.
        # This service method just handles the creation.
        tool = Tool.objects.create(
            owner_id=owner_id,
            name=name,
            tool_type=tool_type,
            definition=definition,
            is_system_tool=False # User-created tools are never system tools
        )
        return tool