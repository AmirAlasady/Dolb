# MS13/MS13/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('ms13/admin/', admin.site.urls),
    path('ms13/api/v1/lrs/', include('lrs.api_urls')),
]