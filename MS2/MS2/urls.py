
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Wrap all paths under the 'ms2/' prefix
    path('ms2/', include([
        path('admin/', admin.site.urls),
        path('api/v1/', include('project.urls')),
        path('internal/v1/', include('projectsinternal.internal_urls')),
    ]))
]