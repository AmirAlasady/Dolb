from rest_framework import permissions
import uuid # Import the uuid module

class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit or view it.
    This version is robust against type mismatches (str vs. UUID).
    """
    def has_object_permission(self, request, view, obj):
        """
        Return `True` if permission is granted, `False` otherwise.
        """
        # obj is the Node instance from the database. obj.owner_id is a UUID object.
        # request.user is the TokenUser from the JWT. request.user.id can be str or UUID.
        
        # --- THE FIX IS HERE ---
        # We convert both the object's owner_id and the user's id to strings
        # before comparing them. This ensures a reliable, type-safe comparison.
        try:
            # Ensure the object's owner_id can be represented as a string
            obj_owner_id_str = str(obj.owner_id)
            
            # Ensure the request user's ID can be represented as a string
            request_user_id_str = str(request.user.id)
            
            return obj_owner_id_str == request_user_id_str
            
        except (TypeError, AttributeError):
            # If for some reason either field is missing or invalid, deny permission.
            return False