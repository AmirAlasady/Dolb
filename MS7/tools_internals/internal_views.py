from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db.models import Q
from tools.models import Tool
import uuid

class ValidateToolsAPIView(APIView):
    """
    Internal HTTP endpoint for the Node Service to validate tool ownership
    before creating or updating a node. Mirrors the gRPC ValidateTools logic.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user_id = request.user.id
        tool_ids_str = request.data.get('tool_ids', [])

        if not isinstance(tool_ids_str, list):
            return Response({"error": "'tool_ids' must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            tool_ids = [uuid.UUID(tid) for tid in tool_ids_str]
        except (ValueError, TypeError):
            return Response({"error": "One or more tool IDs are not valid UUIDs."}, status=status.HTTP_400_BAD_REQUEST)

        if not tool_ids:
            return Response(status=status.HTTP_204_NO_CONTENT)

        valid_tool_count = Tool.objects.filter(
            Q(is_system_tool=True) | Q(owner_id=user_id),
            id__in=tool_ids
        ).count()

        if valid_tool_count == len(tool_ids):
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {"error": "One or more tool IDs are invalid or you do not have permission to use them."},
                status=status.HTTP_403_FORBIDDEN
            )