# in aimodels/permissions.py

from rest_framework import permissions
from .models import AIModel

class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        
        # --- START OF DEBUGGING BLOCK ---
        print("\n--- PERMISSION CHECK ---")
        
        # 1. What user object are we getting?
        print(f"Request User Object: {request.user}")
        print(f"Type of Request User: {type(request.user)}")
        
        # 2. What is the ID on that user object?
        user_id = getattr(request.user, 'id', 'USER_ID_NOT_FOUND')
        print(f"Request User ID: {user_id}")
        print(f"Type of User ID: {type(user_id)}")
        
        # 3. What is the owner_id on the database object we're checking?
        owner_id_on_object = getattr(obj, 'owner_id', 'OWNER_ID_NOT_FOUND')
        print(f"Object's Owner ID: {owner_id_on_object}")
        print(f"Type of Object's Owner ID: {type(owner_id_on_object)}")
        
        # 4. What is the result of the comparison?
        is_owner = str(owner_id_on_object) == str(user_id)
        print(f"Comparing '{str(owner_id_on_object)}' == '{str(user_id)}' -> Result: {is_owner}")
        
        print("--- END PERMISSION CHECK ---\n")
        # --- END OF DEBUGGING BLOCK ---

        if request.method in permissions.SAFE_METHODS:
            return True

        if obj.owner_id and request.user and request.user.is_authenticated:
            return str(obj.owner_id) == str(request.user.id)
            
        return False