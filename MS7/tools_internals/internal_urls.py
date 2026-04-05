from django.urls import path
from .internal_views import ValidateToolsAPIView

urlpatterns = [
    # Endpoint for the Node Service to call via HTTP
    path('tools/validate/', ValidateToolsAPIView.as_view(), name='internal-tool-validate'),
]