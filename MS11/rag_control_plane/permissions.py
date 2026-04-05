# rag_control_plane/permissions.py

from rest_framework import permissions
from .models import KnowledgeCollection

class IsCollectionOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of a KnowledgeCollection to access it.
    """
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, KnowledgeCollection):
            # Compare the owner_id on the collection with the user's ID from the JWT.
            return str(obj.owner_id) == str(request.user.id)
        return False