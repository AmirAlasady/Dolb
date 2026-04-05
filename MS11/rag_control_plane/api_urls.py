from django.urls import path
from .views import CollectionListCreateView, CollectionDetailView, FileLinkCreateView , FileLinkDeleteView, CollectionClearView  

urlpatterns = [
    path('projects/<uuid:project_id>/collections/', CollectionListCreateView.as_view(), name='collection-list-create'),
    path('collections/<uuid:pk>/', CollectionDetailView.as_view(), name='collection-detail'),
    path('collections/<uuid:collection_id>/add_file/', FileLinkCreateView.as_view(), name='file-link-create'),
    path('collections/<uuid:collection_id>/files/<uuid:file_id>/', FileLinkDeleteView.as_view(), name='file-link-delete'),
    path('collections/<uuid:collection_id>/clear/', CollectionClearView.as_view(), name='collection-clear'),
   
]