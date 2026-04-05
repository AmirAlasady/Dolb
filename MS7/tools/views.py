# MS7/tools/views.py

import json
from django.conf import settings
import httpx
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from .models import Tool
from .serializers import ToolSerializer, ToolCreateSerializer, ToolUpdateSerializer
from .permissions import IsOwner
from .services import ToolService # <-- Import the service
from messaging.event_publisher import tool_event_publisher  # Import the event publisher


class ToolListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    
    # --- Using the Service Layer ---
    service = ToolService()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ToolCreateSerializer
        return ToolSerializer

    def get_queryset(self):
        """Delegates the logic for fetching accessible tools to the service layer."""
        return self.service.get_user_accessible_tools(user_id=self.request.user.id)

    def perform_create(self, serializer):
        """Delegates the creation logic to the service layer."""
        self.service.create_user_tool(
            owner_id=self.request.user.id,
            **serializer.validated_data
        )

class ToolDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    
    # --- Using the Service Layer ---
    service = ToolService()

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ToolUpdateSerializer
        return ToolSerializer

    def get_object(self):
        """
        Overrides the default get_object to use the service layer for
        permission-aware retrieval.
        """
        tool_id = self.kwargs.get('pk')
        user_id = self.request.user.id
        
        tool = self.service.get_tool_by_id_for_user(tool_id=tool_id, user_id=user_id)
        
        if not tool:
            raise NotFound("Tool not found or you do not have permission to access it.")
        
        # Check object-level write permissions (IsOwner) after retrieving
        self.check_object_permissions(self.request, tool)
        
        return tool

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        tool_id_to_cleanup = str(instance.pk)
        
        # Perform deletion first
        self.perform_destroy(instance)
        
        # Publish event
        try:
            tool_event_publisher.publish_tool_deleted(tool_id=tool_id_to_cleanup)
        except Exception as e:
            print(f"CRITICAL ALERT: Tool {tool_id_to_cleanup} was deleted, but event publishing failed: {e}")

        return Response(status=status.HTTP_204_NO_CONTENT)