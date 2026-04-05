from django.urls import path
from .internal_views import MemoryBucketValidateAPIView

urlpatterns = [
    path('buckets/validate/', MemoryBucketValidateAPIView.as_view(), name='internal-bucket-validate'),
]