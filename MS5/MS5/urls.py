"""
Root URL configuration for the MS5 Inference Service project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Main entry point for all Inference Service API calls.
    # It delegates all requests starting with '/ms5/api/v1/' to the 'inference_engine' app.
    path('ms5/api/v1/', include('inference_engine.api_urls')),

    # Optional: Include the Django admin interface for debugging and management.
    # This will be accessible at '/ms5/admin/' if you configure an admin user.
    path('ms5/admin/', admin.site.urls),
]


