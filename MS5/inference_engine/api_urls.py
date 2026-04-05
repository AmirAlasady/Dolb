from django.urls import path
from .views import *
urlpatterns = [
    path('nodes/<uuid:node_id>/infer/', InferenceAPIView.as_view(), name='node-infer'),
    path('jobs/<uuid:job_id>/', JobCancellationAPIView.as_view(), name='job-cancel'), # <-- ADD THIS

]