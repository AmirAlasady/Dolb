import grpc
from google.protobuf.struct_pb2 import Struct
from django.db.models import Q
import uuid
import logging

from .generated import tool_pb2, tool_pb2_grpc
from tools.models import Tool
from tools.executor import tool_executor

# Configure a logger for this servicer
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS7-gRPC - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ToolServicer(tool_pb2_grpc.ToolServiceServicer):
    """
    Implements the gRPC service methods for the Tool Service.
    This class is the bridge between gRPC requests and the core application logic.
    """

    def ValidateTools(self, request, context):
        logger.info(f"Received ValidateTools request for user '{request.user_id}' with {len(request.tool_ids)} tool(s).")
        try:
            user_id = uuid.UUID(request.user_id)
            tool_ids = [uuid.UUID(tid) for tid in request.tool_ids]
        except ValueError:
            logger.warning("Invalid UUID format in ValidateTools request.")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Invalid UUID format for user_id or tool_ids.")
            return tool_pb2.ValidateToolsResponse()

        if not tool_ids:
            logger.info("ValidateTools request had no tool IDs. Returning authorized.")
            return tool_pb2.ValidateToolsResponse(authorized=True)

        valid_tool_count = Tool.objects.filter(
            Q(is_system_tool=True) | Q(owner_id=user_id),
            id__in=tool_ids
        ).count()

        if valid_tool_count == len(tool_ids):
            logger.info(f"Successfully validated {len(tool_ids)} tools for user '{user_id}'.")
            return tool_pb2.ValidateToolsResponse(authorized=True)
        else:
            error_msg = "One or more tool IDs are invalid or you do not have permission to use them."
            logger.warning(f"Permission denied for user '{user_id}' on tool validation: {error_msg}")
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(error_msg)
            return tool_pb2.ValidateToolsResponse(authorized=False, error_message=error_msg)

    def GetToolDefinitions(self, request, context):
        logger.info(f"Received GetToolDefinitions request for user '{request.user_id}' with {len(request.tool_ids)} tool(s).")
        try:
            user_id = uuid.UUID(request.user_id)
            tool_ids = [uuid.UUID(tid) for tid in request.tool_ids]
        except ValueError:
            logger.warning("Invalid UUID format in GetToolDefinitions request.")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Invalid UUID format for user_id or tool_ids.")
            return tool_pb2.GetToolDefinitionsResponse()

        accessible_tools = Tool.objects.filter(
            Q(is_system_tool=True) | Q(owner_id=user_id),
            id__in=tool_ids
        )

        if accessible_tools.count() != len(tool_ids):
            error_msg = "Could not find all requested tools or permission denied for one or more tools."
            logger.warning(f"Not found or permission denied during GetToolDefinitions: {error_msg}")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(error_msg)
            return tool_pb2.GetToolDefinitionsResponse()

        definitions = [tool.definition for tool in accessible_tools]
        
        proto_definitions = []
        for definition_dict in definitions:
            s = Struct()
            s.update(definition_dict)
            proto_definitions.append(s)

        logger.info(f"Successfully found and returning {len(proto_definitions)} tool definitions.")
        return tool_pb2.GetToolDefinitionsResponse(definitions=proto_definitions)

    def ExecuteMultipleTools(self, request, context):
        logger.info(f"Received ExecuteMultipleTools request for {len(request.tool_calls)} tool call(s).")
        try:
            tool_calls_list = []
            for call in request.tool_calls:
                arguments = dict(call.arguments) if call.arguments else {}
                tool_calls_list.append({
                    'id': call.id,
                    'name': call.name,
                    'arguments': arguments
                })
            
            # Delegate to the robust, parallel executor
            results = tool_executor.execute_parallel_tools(tool_calls_list)
            
            proto_results = [tool_pb2.ToolResult(**res) for res in results]
            logger.info(f"Successfully executed {len(proto_results)} tool(s).")
            return tool_pb2.ExecuteMultipleToolsResponse(results=proto_results)
        except Exception as e:
            logger.error(f"INTERNAL ERROR during ExecuteMultipleTools: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('An internal error occurred in the Tool Service executor.')
            return tool_pb2.ExecuteMultipleToolsResponse()