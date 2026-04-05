from django.urls import path
from .views import ToolListCreateAPIView, ToolDetailAPIView

urlpatterns = [
    path('tools/', ToolListCreateAPIView.as_view(), name='tool-list-create'),
    path('tools/<uuid:pk>/', ToolDetailAPIView.as_view(), name='tool-detail'),
]