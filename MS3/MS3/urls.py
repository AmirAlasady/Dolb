from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Wrap all paths under the 'ms3/' prefix
    path('ms3/', include([
        path('admin/', admin.site.urls),
        path('api/v1/', include('aimodels.urls')),
        path('internal/v1/', include('aimodelsinternal.internal_urls')),
    ]))
]