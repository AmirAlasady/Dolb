from django.contrib import admin
from .models import MemoryBucket, Message
# Register your models here.
admin.site.register(MemoryBucket)
admin.site.register(Message)
