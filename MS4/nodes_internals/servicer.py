import grpc
from google.protobuf.struct_pb2 import Struct
import logging # <-- Add this import

from .generated import node_pb2, node_pb2_grpc
from nodes.repository import NodeRepository

# --- ADD THIS: Configure a simple logger ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ------------------------------------------

class NodeServicer(node_pb2_grpc.NodeServiceServicer):
    def GetNodeDetails(self, request, context):
        # --- REPLACE print() with logger.info() ---
        logger.info(f"gRPC [NodeService]: Received GetNodeDetails request for node_id={request.node_id}")
        repo = NodeRepository()
        
        try:
            node_instance = repo.find_by_id(request.node_id)
            
            if not node_instance:
                logger.warning(f"gRPC [NodeService]: Node with ID {request.node_id} not found.")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Node with ID {request.node_id} not found.")
                return node_pb2.GetNodeDetailsResponse()

            if str(node_instance.owner_id) != request.user_id:
                logger.warning(f"gRPC [NodeService]: Permission denied for user {request.user_id} on node {request.node_id}.")
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details("User does not have permission to access this node.")
                return node_pb2.GetNodeDetailsResponse()

            proto_config = Struct()
            proto_config.update(node_instance.configuration)

            logger.info(f"gRPC [NodeService]: Successfully authorized and found node {request.node_id}.")
            return node_pb2.GetNodeDetailsResponse(
                id=str(node_instance.id),
                project_id=str(node_instance.project_id),
                owner_id=str(node_instance.owner_id),
                name=node_instance.name,
                configuration=proto_config,
                status=node_instance.status
            )
        except Exception as e:
            logger.error(f"gRPC [NodeService]: Internal error - {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f'An internal error occurred: {e}')
            return node_pb2.GetNodeDetailsResponse()