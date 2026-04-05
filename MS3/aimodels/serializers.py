from rest_framework import serializers
from .models import AIModel
import copy 
class AIModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModel
        fields = [
            'id', 'name', 'provider', 'is_system_model', 'owner_id', 
            'configuration', 'capabilities', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        """
        Customizes the output representation.
        - For system models, it shows the full configuration.
        - For user-owned models, it shows the full structure but redacts
          the actual secret values for security.
        """
        # Get the default representation from the parent class
        data = super().to_representation(instance)

        # We only apply redaction if the model is NOT a system model.
        if not instance.is_system_model:
            # Make a deep copy to avoid modifying the original data
            config = copy.deepcopy(data.get('configuration', {}))
            
            # Navigate to the credentials properties
            credentials_properties = config.get('credentials', {}).get('properties', {})
            
            for key, prop_schema in credentials_properties.items():
                # If a property is marked as sensitive, we redact its 'default' value.
                if prop_schema.get('sensitive') is True:
                    prop_schema['default'] = "**********" # Redact the secret
            
            # Replace the configuration in the final output data
            data['configuration'] = config
            
        return data

class AIModelCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=True)
    provider = serializers.CharField(max_length=100, required=True)
    model_name = serializers.CharField(max_length=255, required=True, help_text="The specific model blueprint to use, e.g., 'gemini-1.5-flash'.")
    credentials = serializers.JSONField(required=True, help_text="A JSON object with credentials, e.g., {'api_key': '...'}.")
    parameters = serializers.JSONField(required=False, default={}, help_text="Optional JSON object for parameter overrides.")

    class Meta:
        # This serializer is not tied to a model because it's a custom input format.
        fields = ['name', 'provider', 'model_name', 'credentials', 'parameters']

class AIModelUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=True)
    # Note: We do not include provider or model_name, as these cannot be changed on update.
    credentials = serializers.JSONField(required=True)
    parameters = serializers.JSONField(required=False, default={})

    class Meta:
        fields = ['name', 'credentials', 'parameters']