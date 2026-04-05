# MS13/lrs/views.py

import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.exceptions import ValidationError, NotFound

from .services import LrsService
from .models import LocalModel
from .serializers import LocalModelSerializer 
from .permissions import IsAdminUser

class SearchHuggingFaceView(APIView):
    """
    An admin-only endpoint to search for models on the Hugging Face Hub.
    It proxies the request and annotates results with local status.
    
    GET /ms13/api/v1/lrs/search/?q=<query>
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        query = request.query_params.get('q')
        if not query:
            return Response({"error": "Query parameter 'q' is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        service = LrsService()
        try:
            results = service.search_huggingface(query)
            return Response(results)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred while searching: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LocalModelListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = LocalModel.objects.all().order_by('-created_at')
    serializer_class = LocalModelSerializer

    def create(self, request, *args, **kwargs):
        """
        Overrides the entire create method to return a 202 Accepted response,
        which is the correct pattern for initiating an asynchronous background job.
        """
        # 1. First, validate the incoming data.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        huggingface_id = serializer.validated_data['huggingface_id']

        # 2. Call the service to create the DB record and publish the job.
        service = LrsService()
        try:
            # This returns the model instance that was just created
            local_model = service.initiate_model_download(huggingface_id)
        except Exception as e:
            # Handle errors like the model already existing, etc.
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Instead of returning the object, return a confirmation.
        response_data = {
            "message": "Model download initiated successfully.",
            "status": "downloading",
            "model_id": local_model.id,
            "huggingface_id": local_model.huggingface_id,
            "details": f"You can poll GET /ms13/api/v1/lrs/models/{local_model.id}/ to check the status."
        }
        
        return Response(response_data, status=status.HTTP_202_ACCEPTED)


class LocalModelDetailView(generics.RetrieveAPIView):
    """
    An admin-only endpoint to get the detailed status of a single tracked model.
    
    GET /ms13/api/v1/lrs/models/<uuid>/
    """
    permission_classes = [IsAdminUser]
    queryset = LocalModel.objects.all()
    serializer_class = LocalModelSerializer


class DeployModelView(APIView):
    """
    An admin-only endpoint to deploy a downloaded model. This will start the
    TGI Docker container(s).
    
    POST /ms13/api/v1/lrs/models/<uuid>/deploy/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            num_instances = int(request.data.get('instances', 1))
            if num_instances < 1:
                raise ValidationError("Number of instances must be 1 or greater.")
        except (ValueError, TypeError):
             return Response({"error": "Field 'instances' must be a valid integer."}, status=status.HTTP_400_BAD_REQUEST)

        service = LrsService()
        try:
            service.deploy_model(pk, num_instances)
            return Response({"message": "Deployment process initiated successfully."}, status=status.HTTP_202_ACCEPTED)
        except (NotFound, ValidationError) as e:
            return Response({"error": str(e)}, status=e.status_code)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred during deployment: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StopModelView(APIView):
    """
    An admin-only endpoint to stop all running instances of a model.
    
    POST /ms13/api/v1/lrs/models/<uuid>/stop/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        service = LrsService()
        try:
            service.stop_model(pk)
            return Response({"message": "Stop command issued for all model instances."}, status=status.HTTP_202_ACCEPTED)
        except NotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred while stopping the model: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)