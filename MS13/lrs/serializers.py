from rest_framework import serializers
from .models import LocalModel

class LocalModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalModel
        fields = ['id', 'huggingface_id', 'status', 'local_path', 'capabilities', 'error_message', 'created_at']
        read_only_fields = ['id', 'status', 'local_path', 'capabilities', 'error_message', 'created_at']