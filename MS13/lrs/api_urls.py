# MS13/lrs/api_urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.SearchHuggingFaceView.as_view(), name='hf-search'),
    path('models/', views.LocalModelListCreateView.as_view(), name='model-list-create'),
    path('models/<uuid:pk>/', views.LocalModelDetailView.as_view(), name='model-detail'),
    path('models/<uuid:pk>/deploy/', views.DeployModelView.as_view(), name='model-deploy'),
    path('models/<uuid:pk>/stop/', views.StopModelView.as_view(), name='model-stop'),
]