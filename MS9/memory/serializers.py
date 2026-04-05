from rest_framework import serializers
from .models import MemoryBucket, Message

class MemoryBucketCreateSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(write_only=True)
    class Meta:
        model = MemoryBucket
        fields = ['name', 'project_id', 'memory_type', 'config']

class MemoryBucketUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemoryBucket
        fields = ['name', 'memory_type', 'config']

class MemoryBucketListSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemoryBucket
        fields = ['id', 'name', 'memory_type', 'message_count', 'token_count', 'updated_at']

class MemoryBucketDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemoryBucket
        fields = '__all__'

class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'content', 'timestamp']