from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('ms10/admin/', admin.site.urls),
    path('ms10/api/v1/', include('data.api_urls')),
    # gRPC is handled by a separate management command, not via URLs
]