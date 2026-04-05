# MS11/rag_control_plane/serializers.py

from rest_framework import serializers
from .models import KnowledgeCollection, FileCollectionLink

class KnowledgeCollectionSerializer(serializers.ModelSerializer):
    """
    Serializer for the KnowledgeCollection model. Used for creating,
    updating, and retrieving collection metadata via the REST API.
    """
    project_id = serializers.UUIDField(write_only=True, required=False) # Make it write_only for creation

    class Meta:
        model = KnowledgeCollection
        # List the fields you want to expose in your API
        fields = [
            'id', 
            'project_id', # Included for creation
            'name', 
            'description', 
            'strategy_type', 
            'config', 
            'created_at', 
            'updated_at'
        ]
        # These fields are set automatically by the system or read from the URL,
        # not provided directly by the user in the JSON body.
        read_only_fields = ['id', 'created_at', 'updated_at']

class FileLinkSerializer(serializers.Serializer):
    """
    A simple serializer just for validating the 'file_id' when a user
    links an existing file to a knowledge collection.
    """
    file_id = serializers.UUIDField(required=True)