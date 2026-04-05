from rest_framework import serializers
from .models import StoredFile

class StoredFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoredFile
        fields = ['id', 'filename', 'mimetype', 'size_bytes', 'created_at']
        read_only_fields = fields

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(write_only=True)