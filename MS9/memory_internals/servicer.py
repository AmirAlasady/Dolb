# MS9/memory_internals/servicer.py

import grpc
import uuid
import logging
from google.protobuf.struct_pb2 import Struct
from rest_framework.exceptions import PermissionDenied, NotFound

from memory.models import MemoryBucket
from memory.services import MemoryService
from . import memory_pb2, memory_pb2_grpc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS9-gRPC - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MemoryServicer(memory_pb2_grpc.MemoryServiceServicer):
    def GetHistory(self, request, context):
        logger.info(f"--- gRPC GetHistory Request Received ---")
        logger.info(f"    Bucket ID: {request.bucket_id}")
        logger.info(f"    User ID: {request.user_id}")

        try:
            bucket = MemoryBucket.objects.get(id=request.bucket_id)
            if str(bucket.owner_id) != request.user_id:
                raise PermissionDenied("User does not own this bucket.")
            
            service = MemoryService()
            processed_data = service.get_processed_history(bucket)
            
            # --- THE DEFINITIVE FIX ---
            # The 'history' field in the response MUST be a list of Protobuf Structs.
            # We must iterate over the Python list of dicts and convert each one.
            history_as_structs = []
            if processed_data and processed_data.get("history"):
                for history_item in processed_data["history"]:
                    proto_struct = Struct()
                    # update() correctly handles nested dictionaries and lists.
                    proto_struct.update(history_item)
                    history_as_structs.append(proto_struct)
            
            logger.info(f"Success! Returning {len(history_as_structs)} history items for bucket {request.bucket_id}.")
            
            return memory_pb2.GetHistoryResponse(
                bucket_id=processed_data['bucket_id'],
                memory_type=processed_data['memory_type'],
                history=history_as_structs # <-- Pass the correctly converted list of Structs
            )
            # --- END OF FIX ---
            
        except MemoryBucket.DoesNotExist:
            logger.warning(f"NOT FOUND: Memory bucket '{request.bucket_id}' does not exist.")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Memory bucket not found.")
            return memory_pb2.GetHistoryResponse()
        except PermissionDenied as e:
            logger.warning(f"PERMISSION DENIED for bucket '{request.bucket_id}': {e}")
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(str(e))
            return memory_pb2.GetHistoryResponse()
        except Exception as e:
            logger.error(f"INTERNAL ERROR during GetHistory for bucket '{request.bucket_id}'", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("An internal error occurred in the Memory Service.")
            return memory_pb2.GetHistoryResponse()