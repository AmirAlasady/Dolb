from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Public API for users
    path('ms7/api/v1/', include('tools.api_urls')),

    # Internal HTTP API for other services (like Node Service)
    path('ms7/internal/v1/', include('tools_internals.internal_urls')),

    # Django admin
    path('ms7/admin/', admin.site.urls),
]