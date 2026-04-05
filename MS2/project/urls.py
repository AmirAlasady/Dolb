# in projects/urls.py

from django.urls import path
from .views import ProjectListCreateAPIView, ProjectDetailAPIView

# The app_name helps in namespacing URLs, which is a good practice.
app_name = 'projects'

urlpatterns = [
    # Corresponds to: /ms2/api/v1/project/projects/
    path('projects/', ProjectListCreateAPIView.as_view(), name='project-list-create'),
    
    # Corresponds to: /ms2/api/v1/project/projects/<uuid:pk>/
    # The <uuid:pk> path converter ensures that only valid UUIDs are accepted.
    path('projects/<uuid:pk>/', ProjectDetailAPIView.as_view(), name='project-detail'),
]