# gRPC and HTTP clients
import grpc
import httpx
import asyncio
import json
from app import config
#from app.internals.generated import tool_pb2, tool_pb2_grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct
from app.logging_config import logging


from app.internals.generated import tool_pb2, tool_pb2_grpc
from app.internals.generated import data_pb2, data_pb2_grpc
from app.logging_config import logger # Use the correct logger import

class ToolServiceClient:
    """A client for interacting with the gRPC Tool Service (MS7)."""
    
    async def execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        """
        Executes one or more tools in parallel by calling the Tool Service.
        """
        if not config.TOOL_SERVICE_GRPC_URL:
            logger.error("TOOL_SERVICE_GRPC_URL is not set. Cannot execute tools.")
            return [{"status": "error", "output": "Tool Service is not configured."}]

        try:
            async with grpc.aio.insecure_channel(config.TOOL_SERVICE_GRPC_URL) as channel:
                # --- THIS IS THE CRITICAL FIX: UNCOMMENT THE LOGIC ---
                stub = tool_pb2_grpc.ToolServiceStub(channel)
                
                # --- THE DEFINITIVE TYPE-SAFE TIMEOUT FIX ---
                custom_timeouts = []
                for call in tool_calls:
                    # Gracefully handle if 'arguments' is missing or not a dict
                    args = call.get("arguments")
                    if isinstance(args, dict) and 'timeout' in args:
                        try:
                            # Attempt to convert the timeout value to a float.
                            custom_timeouts.append(float(args['timeout']))
                        except (ValueError, TypeError):
                            logger.warning(f"Could not parse timeout value '{args['timeout']}'. Using default.")
                
                # Use the longest valid timeout, or default to 5 minutes (300.0 seconds).
                rpc_timeout = max(custom_timeouts) if custom_timeouts else 300.0
                # --- END OF FIX ---
                
                proto_tool_calls = []
                for call in tool_calls:
                    arguments = Struct()
                    args_data = call.get("arguments", {})
                    if isinstance(args_data, dict):
                        # Important: Remove the timeout from the payload sent to the tool
                        args_data.pop('timeout', None)
                        arguments.update(args_data)
                    
                    proto_tool_calls.append(tool_pb2.ToolCall(
                        id=call.get("id"), name=call.get("name"), arguments=arguments
                    ))

                request = tool_pb2.ExecuteMultipleToolsRequest(tool_calls=proto_tool_calls)
                logger.info(f"Sending gRPC request to ToolService: ExecuteMultipleTools for {len(proto_tool_calls)} tool(s).")
                response = await stub.ExecuteMultipleTools(request, timeout=rpc_timeout)
                
                # Convert the Protobuf response back to a Python list of dicts
                return [
                    {
                        "tool_call_id": res.tool_call_id,
                        "name": res.name,
                        "status": res.status,
                        "output": res.output
                    }
                    for res in response.results
                ]
                # --- END OF FIX ---
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error executing tools: {e.details()}", exc_info=True)
            # Return an error structure that the agent can understand
            return [
                {
                    "tool_call_id": call.get("id"),
                    "name": call.get("name"),
                    "status": "error",
                    "output": f"Error calling tool service: {e.details()}"
                } for call in tool_calls
            ]


class DataServiceClient:
    """A client for fetching the parsed content of on-the-fly files from MS10."""
    
    async def get_file_content(self, file_id: str, user_id: str) -> dict:
        """
        Fetches and returns the parsed content of a single file from MS10.
        """
        if not config.DATA_SERVICE_GRPC_URL:
            logger.error("DATA_SERVICE_GRPC_URL is not set. Cannot fetch file content.")
            return {"type": "error", "content": "Data Service is not configured."}
            
        logger.info(f"Fetching content for file_id: {file_id}")
        try:
            async with grpc.aio.insecure_channel(config.DATA_SERVICE_GRPC_URL) as channel:
                stub = data_pb2_grpc.DataServiceStub(channel)
                request = data_pb2.GetFileContentRequest(file_id=file_id, user_id=user_id)
                response = await stub.GetFileContent(request, timeout=60.0)
                
                # Convert the proto Struct back to a Python dict
                return MessageToDict(response.content, preserving_proto_field_name=True)
                
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error fetching content for file {file_id}: {e.details()}", exc_info=True)
            return {"type": "error", "content": f"Error fetching file content: {e.details()}"}
        except Exception as e:
            logger.error(f"Unexpected error in DataServiceClient: {e}", exc_info=True)
            return {"type": "error", "content": "Unexpected error fetching file content."}

    # --- ADD THIS NEW METHOD ---
    async def upload_generated_image(self, image_bytes: bytes, user_id: str, project_id: str, jwt_token: str) -> dict:
        """
        Uploads raw image bytes to the internal REST endpoint on the Data Service (MS10),
        acting on behalf of the user.
        """
        if not all([project_id, user_id, jwt_token]):
            raise ValueError("project_id, user_id, and jwt_token are required to upload a generated image.")
            
        # This URL must match the internal endpoint defined in MS10's urls.
        url = f"http://localhost:8010/ms10/internal/v1/projects/{project_id}/upload_generated/"
        
        # The JWT is passed to MS10 to prove this service is acting on the user's behalf.
        headers = { "Authorization": f"Bearer {jwt_token}" }
        files = {'file': ('generated_image.png', image_bytes, 'image/png')}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                logger.info(f"Uploading generated image for user {user_id} to project {project_id}...")
                response = await client.post(url, files=files, headers=headers)
                response.raise_for_status() # Raise an exception for 4xx/5xx errors
                logger.info("Generated image uploaded successfully.")
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to upload generated image to MS10. Status: {e.response.status_code}, Body: {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Network error while trying to upload generated image to MS10: {e}")
                raise