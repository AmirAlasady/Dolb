# MS13/lrs/permissions.py

from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admin users to create or modify objects,
    but allow any authenticated user to view them.
    
    In the context of the LRS, we will lock it down even further in the views
    to be admin-only for all actions. This class is provided for future
    flexibility if you ever want to allow regular users to view the list
    of available local models.
    """
    def has_permission(self, request, view):
        # Read permissions are allowed to any authenticated user,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Write permissions are only allowed to admin users.
        return request.user and request.user.is_staff

class IsAdminUser(permissions.BasePermission):
    """
    The primary permission class for the LRS.
    Allows full access only to admin users (user.is_staff is True).
    Denies access to all regular, non-staff users.
    """
    def has_permission(self, request, view):
        # The request must have a user attached, and that user must be a staff member.
        return request.user and request.user.is_authenticated and request.user.is_staff