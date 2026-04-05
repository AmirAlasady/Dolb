# in aimodels/urls.py

from django.urls import path
from .views import AIModelListCreateAPIView, AIModelDetailAPIView

urlpatterns = [
    # Route for listing all models and creating a new one
    # Handles GET and POST requests.
    path('models/', AIModelListCreateAPIView.as_view(), name='model-list-create'),
    
    # Route for dealing with a specific model by its UUID primary key
    # Handles GET, PUT, and DELETE requests.
    path('models/<uuid:pk>/', AIModelDetailAPIView.as_view(), name='model-detail'),
]