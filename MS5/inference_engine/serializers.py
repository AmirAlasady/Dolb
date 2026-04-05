# MS5/inference_engine/serializers.py

from rest_framework import serializers

class InputObjectSerializer(serializers.Serializer):
    """Defines the structure for a single input item (e.g., a file or image)."""
    type = serializers.ChoiceField(
        choices=["file_id", "image_url", "audio_id"],
        required=True
    )
    id = serializers.CharField(required=False)
    url = serializers.URLField(required=False)
    # Adding source for better metadata tracking
    source = serializers.CharField(required=False, default="unknown") 

    def validate(self, data):
        """Ensure that the correct reference (id or url) is provided for the type."""
        input_type = data.get('type')
        if input_type in ['file_id', 'audio_id'] and not data.get('id'):
            raise serializers.ValidationError(f"Input of type '{input_type}' must have an 'id'.")
        if input_type == 'image_url' and not data.get('url'):
            raise serializers.ValidationError("Input of type 'image_url' must have a 'url'.")
        return data

class InferenceRequestSerializer(serializers.Serializer):
    """
    The definitive, flexible serializer for all inference requests.
    It validates the user's immediate intent for a single execution.
    """
    prompt = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    inputs = InputObjectSerializer(many=True, required=False, default=[])
    
    resource_overrides = serializers.DictField(required=False, default={})
    parameter_overrides = serializers.DictField(required=False, default={})
    output_config = serializers.DictField(required=False, default={})
    
    def validate(self, data):
        """Ensure that at least a prompt or an input is provided."""
        if not data.get('prompt') and not data.get('inputs'):
            raise serializers.ValidationError("An inference request must contain at least a 'prompt' or an 'inputs' array.")
        return data