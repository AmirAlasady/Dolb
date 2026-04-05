from django.contrib import admin

# Register your models here.
from .models import StoredFile

admin.site.register(StoredFile)