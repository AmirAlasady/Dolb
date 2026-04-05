from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('ms11/admin/', admin.site.urls),
    path('ms11/api/v1/', include('rag_control_plane.api_urls')),
    # --- ADD THIS LINE ---
    path('ms11/internal/v1/', include('rag_internals.internal_urls')),
]