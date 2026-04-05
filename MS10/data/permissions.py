from rest_framework import permissions

class IsFileOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return str(obj.owner_id) == str(request.user.id)