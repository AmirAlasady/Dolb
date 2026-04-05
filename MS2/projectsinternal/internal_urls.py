

from django.urls import path
from .internal_views import ProjectAuthorizationView
# The app_name helps in namespacing URLs, which is a good practice.
app_name = 'projectsinternal'

urlpatterns = [

    # The path matches what our NodeService's client expects.
    path('projects/<uuid:project_id>/authorize', ProjectAuthorizationView.as_view(), name='internal-project-authorize'),

]
