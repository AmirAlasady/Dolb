from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Wrap both admin and api under the 'ms1/' prefix
    path('ms1/', include([
        path('admin/', admin.site.urls),
        path('api/v1/auth/', include('accounts.api_urls')),
    ]))
]