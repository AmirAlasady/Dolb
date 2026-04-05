# MS5/inference_internals/clients.py

import grpc
from django.conf import settings
from google.protobuf.json_format import MessageToDict
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

# Import all generated gRPC stubs from the 'generated' sub-package
from .generated import node_pb2, node_pb2_grpc
from .generated import model_pb2, model_pb2_grpc
from .generated import tool_pb2, tool_pb2_grpc
from .generated import memory_pb2, memory_pb2_grpc
from .generated import data_pb2, data_pb2_grpc # <-- NEW
from .generated import rag_pb2, rag_pb2_grpc

class NodeServiceClient:
    """A gRPC client for interacting with the Node Service (MS4)."""
    def get_node_details(self, node_id: str, user_id: str) -> dict:
        try:
            with grpc.insecure_channel(settings.NODE_SERVICE_GRPC_URL) as channel:
                stub = node_pb2_grpc.NodeServiceStub(channel)
                request = node_pb2.GetNodeDetailsRequest(node_id=node_id, user_id=user_id)
                response = stub.GetNodeDetails(request, timeout=10)
                
                # Use preserving_proto_field_name=True to ensure snake_case keys
                return MessageToDict(response, preserving_proto_field_name=True)

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise NotFound(f"Node '{node_id}' not found.")
            if e.code() == grpc.StatusCode.PERMISSION_DENIED:
                raise PermissionDenied(f"Permission denied for node '{node_id}'.")
            raise RuntimeError(f"gRPC error from Node Service: {e.details()}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error in NodeServiceClient: {e}")

class ModelServiceClient:
    """A gRPC client for interacting with the Model Service (MS3)."""
    def get_model_configuration(self, model_id: str, user_id: str) -> dict:
        try:
            with grpc.insecure_channel(settings.MODEL_SERVICE_GRPC_URL) as channel:
                stub = model_pb2_grpc.ModelServiceStub(channel)
                request = model_pb2.GetModelConfigurationRequest(model_id=model_id, user_id=user_id)
                response = stub.GetModelConfiguration(request, timeout=10)
                
                # Use preserving_proto_field_name=True to ensure snake_case keys
                return MessageToDict(response, preserving_proto_field_name=True)
                
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise NotFound(f"Model '{model_id}' not found.")
            if e.code() == grpc.StatusCode.PERMISSION_DENIED:
                raise PermissionDenied(f"Permission denied for model '{model_id}'.")
            raise RuntimeError(f"gRPC error from Model Service: {e.details()}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error in ModelServiceClient: {e}")

class ToolServiceClient:
    """A gRPC client for interacting with the Tool Service (MS7)."""
    def get_tool_definitions(self, tool_ids: list[str], user_id: str) -> list[dict]:
        try:
            with grpc.insecure_channel(settings.TOOL_SERVICE_GRPC_URL) as channel:
                stub = tool_pb2_grpc.ToolServiceStub(channel)
                request = tool_pb2.GetToolDefinitionsRequest(user_id=user_id, tool_ids=tool_ids)
                response = stub.GetToolDefinitions(request, timeout=10)
                
                # Use preserving_proto_field_name=True for each item in the list
                return [MessageToDict(d, preserving_proto_field_name=True) for d in response.definitions]
                
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise NotFound("One or more requested tools were not found.")
            raise RuntimeError(f"gRPC error from Tool Service: {e.details()}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error in ToolServiceClient: {e}")

class MemoryServiceClient:
    """A gRPC client for interacting with the Memory Service (MS9)."""
    def get_history(self, bucket_id: str, user_id: str) -> dict:
        if not settings.MEMORY_SERVICE_GRPC_URL:
            print("WARNING: MEMORY_SERVICE_GRPC_URL not set in .env. Skipping memory call.")
            return {} # Return empty dict to avoid crashes if the service isn't configured

        try:
            with grpc.insecure_channel(settings.MEMORY_SERVICE_GRPC_URL) as channel:
                stub = memory_pb2_grpc.MemoryServiceStub(channel)
                request = memory_pb2.GetHistoryRequest(bucket_id=bucket_id, user_id=user_id)
                
                print(f"DEBUG [MS5]: Calling GetHistory for bucket: {bucket_id}")
                response = stub.GetHistory(request, timeout=10)
                
                # Use preserving_proto_field_name=True to ensure snake_case keys
                return MessageToDict(response, preserving_proto_field_name=True)

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise NotFound(f"Memory bucket '{bucket_id}' not found.")
            if e.code() == grpc.StatusCode.PERMISSION_DENIED:
                raise PermissionDenied(f"Permission denied for memory bucket '{bucket_id}'.")
            raise RuntimeError(f"A gRPC error occurred while contacting the Memory Service: {e.details()}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error in MemoryServiceClient: {e}")
        
class DataServiceClient:
    """A gRPC client for interacting with the Data Service (MS10)."""

    def get_file_metadata(self, file_ids: list[str], user_id: str) -> list[dict]:
        """
        Fetches metadata for a list of files, validating ownership.
        Used by the orchestrator for pre-flight validation checks.
        """
        if not file_ids:
            return []
        
        if not settings.DATA_SERVICE_GRPC_URL:
            raise ValidationError("Data Service is not configured in the environment.")
            
        try:
            with grpc.insecure_channel(settings.DATA_SERVICE_GRPC_URL) as channel:
                stub = data_pb2_grpc.DataServiceStub(channel)
                request = data_pb2.GetFileMetadataRequest(file_ids=file_ids, user_id=user_id)
                response = stub.GetFileMetadata(request, timeout=10)
                
                # Convert the list of Protobuf messages to a list of Python dicts
                return [MessageToDict(m, preserving_proto_field_name=True) for m in response.metadata]

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise NotFound("One or more of the specified files were not found or you do not have permission to use them.")
            raise RuntimeError(f"gRPC error from Data Service (GetFileMetadata): {e.details()}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error in DataServiceClient: {e}")
        


class RAGServiceClient:
    """A gRPC client for interacting with the RAG Service (MS11)."""
    def RetrieveRelevantChunks(self, collection_id: str, user_id: str, query: str, top_k: int = 3) -> dict:
        """
        Calls the RAG service to perform a similarity search and retrieve text chunks.
        """
        try:
            with grpc.insecure_channel(settings.RAG_SERVICE_GRPC_URL) as channel:
                stub = rag_pb2_grpc.RAGServiceStub(channel)
                request = rag_pb2.RetrieveRequest(
                    collection_id=collection_id,
                    user_id=user_id,
                    query=query,
                    top_k=top_k
                )
                response = stub.RetrieveRelevantChunks(request, timeout=15) # Longer timeout for embedding+search
                # The response itself contains the list of chunks, so we convert the whole thing.
                return MessageToDict(response, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise NotFound(f"RAG collection '{collection_id}' not found or permission denied.")
            raise RuntimeError(f"A gRPC error occurred while contacting the RAG Service: {e.details()}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error in RAGServiceClient: {e}")