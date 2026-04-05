from django.urls import path
from . import views

urlpatterns = [
    path('buckets/', views.MemoryBucketCreateAPIView.as_view(), name='bucket-create'),
    path('projects/<uuid:project_id>/buckets/', views.MemoryBucketListAPIView.as_view(), name='bucket-list'),
    path('buckets/<uuid:pk>/', views.MemoryBucketDetailAPIView.as_view(), name='bucket-detail'),
    path('buckets/<uuid:pk>/clear/', views.MemoryBucketClearAPIView.as_view(), name='bucket-clear'),
    path('buckets/<uuid:bucket_id>/messages/', views.MessageListAPIView.as_view(), name='message-list'),
    path('messages/<uuid:pk>/', views.MessageDetailAPIView.as_view(), name='message-detail'),
    # --- NEW IMPORT/EXPORT URLS ---
    path('buckets/import/', views.MemoryBucketImportAPIView.as_view(), name='bucket-import'),
    path('buckets/<uuid:pk>/export/', views.MemoryBucketExportAPIView.as_view(), name='bucket-export'),
    # --- END OF NEW URLS ---
]