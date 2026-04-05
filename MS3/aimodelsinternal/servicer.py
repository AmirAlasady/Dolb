import grpc
from google.protobuf.struct_pb2 import Struct
from rest_framework.exceptions import PermissionDenied, ValidationError
import logging

from . import model_pb2, model_pb2_grpc
from aimodels.services import AIModelService

# Configure a logger for this servicer
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS3-gRPC - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelServicer(model_pb2_grpc.ModelServiceServicer):
    """
    Implements the gRPC service for AI Models.
    It acts as a bridge between the gRPC requests and the Django service layer.
    """

    def GetModelConfiguration(self, request, context):
        """
        Handles the gRPC request to get a model's full configuration.
        """
        logger.info(f"Received GetModelConfiguration request for model_id='{request.model_id}' from user_id='{request.user_id}'")
        
        service = AIModelService()
        
        try:
            # The get_model_by_id method contains all authorization logic.
            model_instance = service.get_model_by_id(
                model_id=request.model_id,
                user_id=request.user_id
            )
            
            # This is where decryption would happen in a real implementation.
            decrypted_config = model_instance.configuration

            # Convert the Python dict configuration to a protobuf Struct
            proto_config = Struct()
            proto_config.update(decrypted_config)
            
            logger.info(f"Successfully found and authorized model '{request.model_id}'. Returning configuration.")
            return model_pb2.GetModelConfigurationResponse(
                provider=model_instance.provider,
                configuration=proto_config,
                capabilities=model_instance.capabilities
            )

        except PermissionDenied as e:
            logger.warning(f"PERMISSION DENIED for model '{request.model_id}': {e}")
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(str(e))
            return model_pb2.GetModelConfigurationResponse()
        except ValidationError as e: # This handles 'Not Found' from your service
            logger.warning(f"NOT FOUND for model '{request.model_id}': {e}")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(str(e))
            return model_pb2.GetModelConfigurationResponse()
        except Exception as e:
            logger.error(f"INTERNAL ERROR during GetModelConfiguration for model '{request.model_id}': {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('An internal error occurred in the Model Service.')
            return model_pb2.GetModelConfigurationResponse()