import grpc
from google.protobuf.struct_pb2 import Struct

# Import generated classes and your existing repository/permissions
from . import node_pb2, node_pb2_grpc
from .repository import NodeRepository
from .models import Node

class NodeServicer(node_pb2_grpc.NodeServiceServicer):
    """Implements the gRPC service for Nodes."""

    def GetNodeDetails(self, request, context):
        print(f"gRPC [NodeService]: Received GetNodeDetails request for node_id={request.node_id}")
        repo = NodeRepository()
        
        try:
            node_instance = repo.find_by_id(request.node_id)
            
            if not node_instance:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Node with ID {request.node_id} not found.")
                return node_pb2.GetNodeDetailsResponse()

            # --- AUTHORIZATION CHECK ---
            if str(node_instance.owner_id) != request.user_id:
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details("User does not have permission to access this node.")
                return node_pb2.GetNodeDetailsResponse()

            # Convert Python dict to protobuf Struct
            proto_config = Struct()
            proto_config.update(node_instance.configuration)

            return node_pb2.GetNodeDetailsResponse(
                id=str(node_instance.id),
                project_id=str(node_instance.project_id),
                owner_id=str(node_instance.owner_id),
                name=node_instance.name,
                configuration=proto_config,
                status=node_instance.status
            )

        except Exception as e:
            print(f"gRPC [NodeService]: Internal error - {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('An internal error occurred.')
            return node_pb2.GetNodeDetailsResponse()