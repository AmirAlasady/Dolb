from rest_framework import serializers
from .models import Node

class NodeSerializer(serializers.ModelSerializer):
    """
    The primary, read-only serializer for displaying Node objects.
    Used for all GET requests (list and detail).
    """
    class Meta:
        model = Node
        fields = [
            'id', 'project_id', 'owner_id', 'name', 'status', 
            'configuration', 'created_at', 'updated_at'
        ]
        read_only_fields = fields # Make all fields read-only by default

class NodeDraftCreateSerializer(serializers.Serializer):
    """
    Used ONLY for the STAGE 1 `POST /nodes/draft/` endpoint.
    Strictly validates only the name and project_id.
    """
    name = serializers.CharField(max_length=255, required=True)
    project_id = serializers.UUIDField(required=True)

    def to_internal_value(self, data):
        # This ensures that ONLY 'name' and 'project_id' are processed.
        # Any other keys in the user's request body are completely discarded.
        validated_data = {
            'name': data.get('name'),
            'project_id': data.get('project_id'),
        }
        return super().to_internal_value(validated_data)

class NodeConfigureModelSerializer(serializers.Serializer):
    """
    Used ONLY for the STAGE 2 `POST /nodes/{pk}/configure-model/` endpoint.
    Validates only the model_id.
    """
    model_id = serializers.UUIDField(required=True)

class NodeUpdateSerializer(serializers.Serializer):
    """
    Used for the `PUT /nodes/{pk}/` endpoint.
    Allows updates to the name and the configuration values.

    The primary security function of this serializer is to explicitly
    REJECT any request that attempts to change the 'model_id' within the configuration.
    All other structural and logical validation is handled by the service layer.
    """
    name = serializers.CharField(max_length=255, required=True)
    configuration = serializers.JSONField(required=True) # Using JSONField for maximum flexibility

    def validate_configuration(self, value):
        """
        Validates the incoming configuration data.
        """
        # Ensure the incoming data is a dictionary.
        if not isinstance(value, dict):
            raise serializers.ValidationError("Configuration must be a dictionary.")
            
        # THE ONE CRITICAL CHECK: Prohibit changing the model_id.
        model_config = value.get("model_config")
        if model_config and isinstance(model_config, dict) and "model_id" in model_config:
            raise serializers.ValidationError({
                "model_config.model_id": "Changing the model is not permitted on this endpoint. Please use the '/configure-model' endpoint to reconfigure the node with a new model."
            })
        
        # No other structural validation is needed here. The service layer's
        # template merging and `_validate_resources` call will handle ensuring
        # the user only provides valid keys and resource IDs.

        return value