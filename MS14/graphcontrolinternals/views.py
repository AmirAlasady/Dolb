# MS14/graphcontrolinternals/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from graphcontrol.models import GNode

class NodeDeletionWebhookView(APIView):
    """
    Received calls from MS4 when a Node is deleted.
    Removes the reference from any GNode using it.
    """
    # No permission class (or use a shared secret permission) because this call comes from MS4 backend
    permission_classes = [] 

    def post(self, request):
        ms4_node_id = request.data.get("ms4_node_id")
        if not ms4_node_id:
            return Response({"error": "ms4_node_id required"}, status=status.HTTP_400_BAD_REQUEST)

        # Bulk update to remove reference. Fast and efficient.
        updated_count = GNode.objects.filter(ms4_node_id=ms4_node_id).update(ms4_node_id=None)
        
        print(f"Webhook: Detached deleted MS4 node {ms4_node_id} from {updated_count} GNodes.")
        
        return Response({"status": "acknowledged", "detached_count": updated_count})