# MS14/graphcontrolinternals/urls.py
from django.urls import path
from .views import NodeDeletionWebhookView

urlpatterns = [
    path('webhook/node-deleted/', NodeDeletionWebhookView.as_view(), name='webhook-node-deleted'),
]