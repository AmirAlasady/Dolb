# in projects/serializers.py

from rest_framework import serializers
from .models import Project

class ProjectSerializer(serializers.ModelSerializer):
    """
    Serializer for the Project model.
    Handles serialization for list and detail views.
    """
    
    # We make owner_id read-only because it should be set automatically
    # based on the authenticated user making the request, not from user input.
    owner_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Project
        # The fields list remains the same, but the field types are now consistent.
        fields = ['id', 'name', 'owner_id', 'created_at', 'updated_at', 'metadata']
        read_only_fields = ['id', 'owner_id', 'created_at', 'updated_at']

class ProjectCreateSerializer(serializers.ModelSerializer):
    """
    A more constrained serializer specifically for creating projects.
    This serializer does not need to be changed, as it doesn't include the owner_id field.
    """
    class Meta:
        model = Project
        fields = ['name', 'metadata']
        extra_kwargs = {
            'metadata': {'required': False}
        }