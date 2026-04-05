# MS11/rag_internals/internal_urls.py
from django.urls import path
from .internal_views import CollectionValidateAPIView

urlpatterns = [
    path('collections/validate/', CollectionValidateAPIView.as_view(), name='internal-collection-validate'),
]