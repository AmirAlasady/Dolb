# MS4/nodes_internals/internal_urls.py
from django.urls import path
from .internal_views import NodeClaimView, NodeUnclaimView

urlpatterns = [

    path('nodes/<uuid:pk>/claim/', NodeClaimView.as_view(), name='internal-node-claim'),
    path('nodes/<uuid:pk>/unclaim/', NodeUnclaimView.as_view(), name='internal-node-unclaim'),
]