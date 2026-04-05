
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Wrap all paths under the 'ms4/' prefix
    path('ms4/', include([
        path('admin/', admin.site.urls),
        path('api/v1/', include('nodes.urls')),
        path('internal/v1/', include('nodes_internals.internal_urls')), # <-- ADD INTERNAL URLS
    ]))
]