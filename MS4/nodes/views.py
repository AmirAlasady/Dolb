# MS4/nodes/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied
from django.db import transaction
import uuid
import json

from .models import Node, NodeStatus
from .repository import NodeRepository
from .services import NodeService
from .serializers import (
    NodeSerializer, 
    NodeUpdateSerializer, 
    NodeDraftCreateSerializer, 
    NodeConfigureModelSerializer
)
from .permissions import IsOwner
from nodes_internals.clients import GraphControlClient

# --- STAGE 1 & 2: NODE CREATION WORKFLOW VIEWS ---

class NodeDraftCreateAPIView(APIView):
    """
    Handles STAGE 1 of node creation: creating a placeholder 'draft' node.
    Endpoint: POST /ms4/api/v1/nodes/draft/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = NodeDraftCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = NodeService()
        try:
            draft_node = service.create_draft_node(
                jwt_token=str(request.auth),
                user_id=request.user.id,
                project_id=serializer.validated_data['project_id'],
                name=serializer.validated_data['name']
            )
            # Use the general purpose serializer for the response
            response_serializer = NodeSerializer(draft_node)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except (PermissionDenied, NotFound) as e:
            return Response({"error": str(e)}, status=e.status_code)
        except Exception as e:
            # Catch any other unexpected errors from the service layer
            return Response({"error": f"An unexpected server error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NodeConfigureModelAPIView(APIView):
    """
    Handles STAGE 2 of node creation: linking a model and generating the config template.
    Endpoint: POST /ms4/api/v1/nodes/{pk}/configure-model/
    """
    permission_classes = [permissions.IsAuthenticated, IsOwner] # IsOwner handles ownership check
    
    def get_object(self, pk):
        repo = NodeRepository()
        node = repo.find_by_id(pk)
        if not node:
            raise NotFound("Node not found.")
        
        # This will run the IsOwner permission check on the fetched object
        self.check_object_permissions(self.request, node)

      
        return node

    def post(self, request, pk):
        print(f"Configuring model for node with ID: {pk}")
        node = self.get_object(pk)
        print(f"Node found: {node.id}")
        serializer = NodeConfigureModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = NodeService()
        try:
            print(f"Configuring node {node.id} with model ID: {serializer.validated_data['model_id']}")
            configured_node = service.configure_node_model(
                jwt_token=str(request.auth),
                node=node,
                model_id=serializer.validated_data['model_id']
            )
            print(f"Node {node.id} configured successfully with model ID: {serializer.validated_data['model_id']}")
            response_serializer = NodeSerializer(configured_node)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        except (PermissionDenied, NotFound, ValidationError) as e:
            return Response({"error": str(e)}, status=e.status_code)
        except Exception as e:
            return Response({"error": f"An unexpected server error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- STANDARD CRUD VIEWS FOR CONFIGURED NODES ---

class NodeListAPIView(APIView):
    """
    Handles LISTING nodes within a project. The POST/Create logic has been moved.
    Endpoint: GET /ms4/api/v1/projects/{project_id}/nodes/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        service = NodeService()
        jwt_token = str(request.auth)
        
        try:
            nodes = service.get_nodes_for_project(
                project_id=project_id, 
                user_id=request.user.id, 
                jwt_token=jwt_token
            )
            serializer = NodeSerializer(nodes, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (PermissionDenied, NotFound) as e:
            return Response({"error": str(e)}, status=e.status_code)

class NodeDetailAPIView(APIView):
    """
    Handles GET, PUT, DELETE for a single, fully configured node.
    Endpoints:
    - GET /ms4/api/v1/nodes/{pk}/
    - PUT /ms4/api/v1/nodes/{pk}/
    - DELETE /ms4/api/v1/nodes/{pk}/
    """
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_object(self, pk):
        repo = NodeRepository()
        node = repo.find_by_id(pk)
        if not node:
            raise NotFound("Node not found.")
        self.check_object_permissions(self.request, node)
        return node
        
    def get(self, request, pk):
        node = self.get_object(pk)
        serializer = NodeSerializer(node)
        return Response(serializer.data)

    def put(self, request, pk):
        service = NodeService()
        node_to_update = self.get_object(pk)
        
        serializer = NodeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        jwt_token = str(request.auth)
        validated_data = serializer.validated_data
        
        updated_node = service.update_node(
            jwt_token=jwt_token,
            node=node_to_update,
            name=validated_data['name'],
            configuration=validated_data['configuration']
        )
        
        response_serializer = NodeSerializer(updated_node)
        return Response(response_serializer.data)

    def delete(self, request, pk):
        service = NodeService()
        node_to_delete = self.get_object(pk)
        if node_to_delete.is_used_in_graph:
            print(f"Node {node_to_delete.id} is marked as used in a graph. Notifying MS14...")
            # Notify MS14 to detach it
            client = GraphControlClient()
            client.notify_node_deletion(str(node_to_delete.id))
        service.delete_node(node_to_delete)
        return Response(status=status.HTTP_204_NO_CONTENT)



# MS4/nodes_internals/internal_views.py
 
# --- INTERNAL WEBHOOK VIEW ---


"""
class IsInternalServicePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # In a real system, this would be more robust (e.g., shared secret header).
        return request.user and request.user.is_authenticated

class ResourceDeletionHookAPIView(APIView):
    permission_classes = [IsInternalServicePermission]

    @transaction.atomic
    def post(self, request):
        resource_type = request.data.get('resource_type')
        resource_id = request.data.get('resource_id')

        if not resource_type or not resource_id:
            return Response({"error": "Missing 'resource_type' or 'resource_id'."}, status=status.HTTP_400_BAD_REQUEST)

        updated_count = 0
        message = ""

        if resource_type == 'model':
            nodes_to_update = Node.objects.select_for_update().filter(
                configuration__model_config__model_id=resource_id
            ).exclude(status=NodeStatus.INACTIVE)
            updated_count = nodes_to_update.update(status=NodeStatus.INACTIVE)
            message = f"Inactivated {updated_count} nodes."
        elif resource_type == 'tool':
            # SQLite-compatible workaround
            print("Checking tool configurations...")
            candidate_nodes = Node.objects.select_for_update().filter(
                status__in=[NodeStatus.ACTIVE, NodeStatus.ALTERED],
                configuration__has_key='tool_config',
                configuration__tool_config__has_key='tool_ids'
            )
            nodes_to_process = []
            print(f"Found {candidate_nodes.count()} candidate nodes.")
            for node in candidate_nodes:
                tool_ids = node.configuration.get('tool_config', {}).get('tool_ids', [])
                if isinstance(tool_ids, list) and resource_id in tool_ids:
                    nodes_to_process.append(node)
            print(f"Nodes to process: {len(nodes_to_process)}")
            if nodes_to_process:
                for node in nodes_to_process:
                    node.configuration['tool_config']['tool_ids'].remove(resource_id)
                    node.status = NodeStatus.ALTERED
                    node.save()
                updated_count = len(nodes_to_process)
            message = f"Removed tool and altered {updated_count} nodes."
        else:
             return Response({"error": f"Unknown resource_type: {resource_type}"}, status=status.HTTP_400_BAD_REQUEST)
        print(f"Processed {updated_count} nodes for resource type '{resource_type}' with ID '{resource_id}'.")
        return Response(
            {"message": f"Processed deletion for {resource_type}:{resource_id}. {message}"},
            status=status.HTTP_200_OK
        )
"""