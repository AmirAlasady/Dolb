from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from nodes.models import Node

class NodeClaimView(APIView):
    """
    Called by MS14 when it links a GNode to this MS4 Node.
    Sets is_used_in_graph = True.
    """
    permission_classes = [permissions.IsAuthenticated] # User JWT from MS14

    def post(self, request, pk):
        node = get_object_or_404(Node, pk=pk)
        
        # Verify ownership (The user making the request in MS14 must own this node)
        if str(node.owner_id) != str(request.user.id):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
            
        node.is_used_in_graph = True
        node.save(update_fields=['is_used_in_graph'])
        return Response({"status": "claimed"}, status=status.HTTP_200_OK)

class NodeUnclaimView(APIView):
    """
    Called by MS14 when it unlinks/detaches a GNode.
    Sets is_used_in_graph = False.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        node = get_object_or_404(Node, pk=pk)
        
        if str(node.owner_id) != str(request.user.id):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        node.is_used_in_graph = False
        node.save(update_fields=['is_used_in_graph'])
        return Response({"status": "unclaimed"}, status=status.HTTP_200_OK)