from rest_framework import serializers
from .models import Tool

class ToolSerializer(serializers.ModelSerializer):
    """
    General purpose serializer for reading and listing tools.
    """
    owner_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Tool
        fields = [
            'id', 'name', 'tool_type', 'definition',
            'is_system_tool', 'owner_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_system_tool', 'owner_id', 'created_at', 'updated_at']

class ToolCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new user-defined tool.
    Validates the structure of the 'definition' field.
    """
    class Meta:
        model = Tool
        fields = ['name', 'tool_type', 'definition']

    def validate_definition(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Definition must be a valid JSON object.")
        if "name" not in value or "description" not in value or "parameters" not in value:
            raise serializers.ValidationError("Definition must contain 'name', 'description', and 'parameters' keys.")
        if "execution" not in value:
            raise serializers.ValidationError("Definition must contain an 'execution' block.")
        
        execution_config = value.get("execution")
        exec_type = execution_config.get("type")

        if exec_type == "webhook":
            if "url" not in execution_config:
                raise serializers.ValidationError("Webhook execution requires a 'url'.")
        elif exec_type == "internal_function":
            # This is a system-level property and shouldn't be set by users.
            # We can add a check to prevent users from trying to create internal tools.
            raise serializers.ValidationError("User-defined tools cannot be of type 'internal_function'.")
        else:
            raise serializers.ValidationError(f"Invalid execution type: '{exec_type}'. Must be 'webhook'.")
            
        return value

class ToolUpdateSerializer(ToolCreateSerializer):
    """
    Serializer for updating an existing user-defined tool.
    Inherits validation from the create serializer.
    """
    pass