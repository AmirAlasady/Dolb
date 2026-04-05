# MS9/memory/permissions.py

from rest_framework import permissions
from .models import MemoryBucket, Message

class IsBucketOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of a MemoryBucket to access it.
    This also handles nested objects like Messages by checking the ownership
    of the parent bucket.
    """
    def has_object_permission(self, request, view, obj):
        # --- THE FIX IS HERE: Explicitly check the type of the object ---
        
        owner_id_to_check = None

        if isinstance(obj, MemoryBucket):
            # If the object is a MemoryBucket, its owner_id is directly on it.
            owner_id_to_check = obj.owner_id
        
        elif isinstance(obj, Message):
            # If the object is a Message, we must check the owner_id of its parent bucket.
            owner_id_to_check = obj.bucket.owner_id
        
        else:
            # If we get an unexpected object type, deny permission by default.
            return False

        # --- END OF FIX ---

        # Now perform the actual comparison.
        # Ensure we're comparing string versions to avoid UUID object issues.
        if owner_id_to_check and request.user and request.user.is_authenticated:
            return str(owner_id_to_check) == str(request.user.id)
            
        return False