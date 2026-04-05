from django.shortcuts import render

# Create your views here.
# MS11/rag_internals/internal_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
import uuid

from rag_control_plane.models import KnowledgeCollection

class CollectionValidateAPIView(APIView):
    """
    Internal HTTP endpoint for the Node Service (MS4) to validate that a user
    owns a list of knowledge collection IDs before linking them to a node.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user_id = request.user.id
        collection_ids_str = request.data.get('collection_ids', [])

        if not isinstance(collection_ids_str, list):
            return Response({"error": "'collection_ids' must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            collection_ids = [uuid.UUID(cid) for cid in collection_ids_str]
        except (ValueError, TypeError):
            return Response({"error": "One or more collection IDs are not valid UUIDs."}, status=status.HTTP_400_BAD_REQUEST)

        if not collection_ids:
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Count how many of the requested collections are actually owned by this user.
        valid_collection_count = KnowledgeCollection.objects.filter(
            owner_id=user_id,
            id__in=collection_ids
        ).count()

        if valid_collection_count == len(collection_ids):
            # The user owns all the collections.
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            # The user is trying to link a collection they don't own or that doesn't exist.
            return Response(
                {"error": "One or more knowledge collection IDs are invalid or you do not have permission to use them."},
                status=status.HTTP_403_FORBIDDEN
            )