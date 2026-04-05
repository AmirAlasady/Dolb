# MS9/memory_internals/internal_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db.models import Q
from memory.models import MemoryBucket
import uuid

class IsInternalServicePermission(permissions.BasePermission):
    """
    In a real system, this would be more robust (e.g., shared secret header).
    For now, we trust any authenticated request to this internal endpoint.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

class MemoryBucketValidateAPIView(APIView):
    """
    Internal HTTP endpoint for the Node Service (MS4) to validate that a user
    owns a list of memory bucket IDs before linking them to a node.
    """
    permission_classes = [IsInternalServicePermission]

    def post(self, request):
        user_id = request.user.id
        bucket_ids_str = request.data.get('bucket_ids', [])

        if not isinstance(bucket_ids_str, list):
            return Response({"error": "'bucket_ids' must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            bucket_ids = [uuid.UUID(bid) for bid in bucket_ids_str]
        except (ValueError, TypeError):
            return Response({"error": "One or more bucket IDs are not valid UUIDs."}, status=status.HTTP_400_BAD_REQUEST)

        if not bucket_ids:
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Count how many of the requested buckets are actually owned by this user.
        valid_bucket_count = MemoryBucket.objects.filter(
            owner_id=user_id,
            id__in=bucket_ids
        ).count()

        if valid_bucket_count == len(bucket_ids):
            # The user owns all the buckets they are trying to link.
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            # The user is trying to link a bucket they don't own or that doesn't exist.
            return Response(
                {"error": "One or more memory bucket IDs are invalid or you do not have permission to use them."},
                status=status.HTTP_403_FORBIDDEN
            )