from rest_framework import permissions

class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to perform actions on it.
    """

    def has_object_permission(self, request, view, obj):
        """
        Return `True` if permission is granted, `False` otherwise.
        """
        # The 'obj' is the Project instance that the view is trying to access.
        # We check if the 'owner_id' stored on the project object matches
        # the 'id' of the user making the request.

        # --- THE FIX IS HERE ---
        # We explicitly convert both IDs to strings before comparing them.
        # This is the most robust method as it avoids any potential type
        # mismatches between a UUID object and its string representation.
        if obj.owner_id and request.user and request.user.is_authenticated:
            return str(obj.owner_id) == str(request.user.id)
            
        return False