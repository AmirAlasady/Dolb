from messaging.event_publisher import memory_event_publisher
from django.shortcuts import render
from django.http import JsonResponse
import uuid
import json # <-- Add this import at the top of the file
from django.http import HttpResponse 
# Create your views here.
from rest_framework import generics, views, status, permissions
from rest_framework.response import Response
from .models import MemoryBucket, Message
from .permissions import IsBucketOwner
from .services import MemoryService
from .serializers import *
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

class MemoryBucketCreateAPIView(views.APIView):
    """
    Handles the creation of a new MemoryBucket.
    Uses a custom 'create' method to use different serializers for
    request validation and response formatting.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 1. Use the strict "Create" serializer to validate the incoming request data.
        write_serializer = MemoryBucketCreateSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        
        service = MemoryService()
        try:
            # 2. Call the service layer to perform the creation logic.
            #    The service method will return the newly created model instance.
            new_bucket = service.create_bucket(
                owner_id=request.user.id,
                jwt_token=str(request.auth),
                **write_serializer.validated_data
            )
            
            # 3. Use the more detailed "DetailSerializer" to create the response data.
            #    This serializer includes the 'id' and all other fields.
            read_serializer = MemoryBucketDetailSerializer(new_bucket)
            
            # 4. Return a 201 Created response with the full object data.
            return Response(read_serializer.data, status=status.HTTP_201_CREATED)

        except (PermissionDenied, NotFound, ValidationError) as e:
             return Response({"error": str(e)}, status=e.status_code)
        except Exception as e:
            return Response({"error": f"An unexpected server error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MemoryBucketListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MemoryBucketListSerializer
    
    def get_queryset(self):
        service = MemoryService()
        project_id = self.kwargs['project_id']
        service._validate_project_ownership(project_id, str(self.request.auth))
        return MemoryBucket.objects.filter(owner_id=self.request.user.id, project_id=project_id)

class MemoryBucketDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, IsBucketOwner]
    queryset = MemoryBucket.objects.all()
    
    def get_serializer_class(self):
        if self.request.method == 'PUT' or self.request.method == 'PATCH':
            return MemoryBucketUpdateSerializer
        return MemoryBucketDetailSerializer
    def destroy(self, request, *args, **kwargs):
        """
        Handles deleting a MemoryBucket and publishes an event upon success.
        """
        # 1. get_object() handles fetching the instance and checking ownership permissions.
        #    If the user is not the owner, it will raise a 403 Forbidden error.
        bucket_to_delete = self.get_object()
        
        service = MemoryService()
        try:
            # 2. Delegate the deletion logic to the service layer.
            #    This returns the ID for use in the event.
            deleted_bucket_id = service.delete_bucket(bucket_to_delete)

            # 3. If deletion was successful, publish the event.
            try:
                memory_event_publisher.publish_bucket_deleted(bucket_id=str(deleted_bucket_id))
            except Exception as e:
                # The bucket was deleted, but the event failed. This is a critical state
                # that should be logged for monitoring.
                print(f"CRITICAL ALERT: MemoryBucket {deleted_bucket_id} was deleted, but the 'memory.bucket.deleted' event publishing failed: {e}")

            # 4. Return a success response to the user.
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            # Catch any unexpected errors during the process.
            return Response(
                {"error": "An unexpected error occurred during bucket deletion."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class MemoryBucketClearAPIView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsBucketOwner]
    
    def post(self, request, pk):
        bucket = generics.get_object_or_404(MemoryBucket.objects.all(), pk=pk)
        self.check_object_permissions(request, bucket)
        bucket.messages.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class MessageListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsBucketOwner]
    serializer_class = MessageSerializer
    
    def get_queryset(self):
        bucket = generics.get_object_or_404(MemoryBucket.objects.all(), id=self.kwargs['bucket_id'])
        self.check_object_permissions(self.request, bucket)
        return Message.objects.filter(bucket=bucket)

class MessageDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, IsBucketOwner]
    serializer_class = MessageSerializer
    queryset = Message.objects.all()


class MemoryBucketExportAPIView(views.APIView):
    """
    Handles the POST request to export a memory bucket's contents as a JSON file.
    This view now returns a proper file download response.
    """
    permission_classes = [permissions.IsAuthenticated, IsBucketOwner]

    def post(self, request, pk):
        bucket = generics.get_object_or_404(MemoryBucket.objects.all(), pk=pk)
        self.check_object_permissions(request, bucket)
        
        service = MemoryService()
        export_data = service.export_bucket_data(bucket)
        
        # --- THE DEFINITIVE FIX IS HERE ---
        
        # 1. Serialize the dictionary to a JSON formatted string.
        #    'indent=2' makes the downloaded file human-readable.
        json_string = json.dumps(export_data, indent=2)
        
        # 2. Create an HttpResponse, not a JsonResponse.
        #    Set the content_type to 'application/json' to tell the client
        #    what kind of file it is.
        response = HttpResponse(json_string, content_type='application/json')
        
        # 3. Set the Content-Disposition header. This is the crucial part that
        #    tells the browser to trigger a "Save As..." dialog instead of
        #    displaying the text in the window.
        filename = f'memory_export_{bucket.name.replace(" ", "_")}_{pk}.json'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # --- END OF FIX ---

        return response
class MemoryBucketImportAPIView(views.APIView):
    """
    Handles the POST request to import a file and create a new memory bucket.
    Uses multipart/form-data for the file upload.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        file_obj = request.FILES.get('file')
        project_id_str = request.data.get('project_id') # Use request.data for form-data

        if not file_obj:
            return Response({"error": "File not provided in 'file' field."}, status=status.HTTP_400_BAD_REQUEST)
        if not project_id_str:
            return Response({"error": "project_id not provided in form data."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project_id = uuid.UUID(project_id_str)
            # Read the entire file content into memory. For very large files,
            # streaming to a temp file on disk would be more memory-efficient.
            file_content = file_obj.read()
        except (ValueError, TypeError):
            return Response({"error": "Invalid project_id UUID format."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Could not read the uploaded file."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        service = MemoryService()
        try:
            # Delegate all validation and creation logic to the service layer
            new_bucket = service.import_bucket_data(
                owner_id=request.user.id,
                project_id=project_id,
                file_content=file_content,
                jwt_token=str(request.auth)
            )
            
            # On success, return the full details of the newly created bucket
            response_serializer = MemoryBucketDetailSerializer(new_bucket)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        except ValidationError as e:
            # Catch the specific validation errors from the service layer
            # and format them into a user-friendly 400 response.
            return Response({"error": "Invalid file content.", "details": e.detail}, status=status.HTTP_400_BAD_REQUEST)