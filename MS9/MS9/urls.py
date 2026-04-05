from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('ms9/admin/', admin.site.urls),
    path('ms9/api/v1/', include('memory.api_urls')),
    path('ms9/internal/v1/', include('memory_internals.internal_urls')),
]