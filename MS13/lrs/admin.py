# MS13/lrs/admin.py
from django.contrib import admin
from .models import LocalModel, ModelInstance

@admin.register(LocalModel)
class LocalModelAdmin(admin.ModelAdmin):
    list_display = ('huggingface_id', 'status', 'updated_at')
    list_filter = ('status',)
    search_fields = ('huggingface_id',)
    readonly_fields = ('local_path', 'capabilities', 'error_message', 'created_at', 'updated_at')

@admin.register(ModelInstance)
class ModelInstanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'local_model', 'status', 'internal_endpoint', 'gpu_uuid', 'last_health_check')
    list_filter = ('status', 'local_model')
    readonly_fields = ('created_at',)