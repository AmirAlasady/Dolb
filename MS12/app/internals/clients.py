import grpc
from google.protobuf.json_format import MessageToDict
from app import config
from app.logging_config import logger
from .generated import data_pb2, data_pb2_grpc, rag_pb2, rag_pb2_grpc

class DataServiceClient:
    async def get_file_content(self, file_id: str, user_id: str) -> dict:
        try:
            async with grpc.aio.insecure_channel(config.DATA_SERVICE_GRPC_URL) as channel:
                stub = data_pb2_grpc.DataServiceStub(channel)
                request = data_pb2.GetFileContentRequest(file_id=file_id, user_id=user_id)
                response = await stub.GetFileContent(request, timeout=300.0) # 5 min timeout for large files
                return MessageToDict(response.content, preserving_proto_field_name=True)
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error fetching content for file {file_id}: {e.details()}", exc_info=True)
            raise

class RAGInternalClient:
    async def update_link_status(self, link_id: str, status: str):
        try:
            async with grpc.aio.insecure_channel(config.RAG_SERVICE_GRPC_URL) as channel:
                # --- THE FIX IS HERE ---
                # We now use the stub for the RAGInternalService, which was
                # generated from the correct, unified proto file.
                stub = rag_pb2_grpc.RAGInternalServiceStub(channel)
                request = rag_pb2.UpdateFileLinkStatusRequest(link_id=link_id, status=status)
                # --- END OF FIX ---

                await stub.UpdateFileLinkStatus(request, timeout=10.0)
                logger.info(f"Successfully updated link {link_id} to status '{status}'.")
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error updating status for link {link_id}: {e.details()}", exc_info=True)
            raise