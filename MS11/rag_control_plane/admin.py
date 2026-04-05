from django.contrib import admin

# Register your models here.
from .models import KnowledgeCollection, FileCollectionLink
admin.site.register(KnowledgeCollection)
admin.site.register(FileCollectionLink)