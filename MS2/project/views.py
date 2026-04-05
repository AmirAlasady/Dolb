from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Project
from .serializers import ProjectSerializer, ProjectCreateSerializer
from .permissions import IsOwner

# sage related and messages stuff
from messaging.event_publisher import event_publisher
from messaging.models import Saga, SagaStep

class ProjectListCreateAPIView(generics.ListCreateAPIView):
    """
    API view to retrieve a list of projects or create a new project.
    * GET: Returns a list of projects owned by the authenticated user.
    * POST: Creates a new project owned by the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        # This remains the same. It correctly selects the serializer
        # for validating the *input* data on a POST.
        if self.request.method == 'POST':
            return ProjectCreateSerializer
        return ProjectSerializer

    def get_queryset(self):
        """
        This view should return a list of all the projects
        for the currently authenticated user.
        """
        user = self.request.user
        return Project.objects.filter(owner_id=user.id)

    # We are replacing perform_create with a full override of the create method.
    def create(self, request, *args, **kwargs):
        """
        Custom create method to use different serializers for input and output.
        """
        # 1. Use the "Create" serializer to validate the incoming request data.
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        
        # 2. Call our custom perform_create logic to save the object.
        # This is where we inject the owner_id.
        instance = self.perform_create(write_serializer)
        
        # 3. Use the more detailed "ProjectSerializer" to create the response data.
        read_serializer = ProjectSerializer(instance)
        
        # 4. Manually construct the 201 Created response.
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        """
        Saves the new instance with the owner_id.
        This method now returns the created instance so the `create` method can use it.
        """
        # The serializer is already validated at this point.
        return serializer.save(owner_id=self.request.user.id)


class ProjectDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    
    # This view remains unchanged, it is already correct.
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()

    def destroy(self, request, *args, **kwargs):
        """
        Overrides the default delete behavior to initiate a deletion saga
        instead of deleting the project directly.
        """
        # self.get_object() is a DRF helper that retrieves the instance based on the URL's pk.
        # It also automatically runs our `IsOwner` permission check.
        # If the user is not the owner, it will raise a 403 Forbidden error before our code runs.
        project = self.get_object() 

        # --- NEW SAGA INITIATION LOGIC ---

        # 1. Idempotency Check: Prevent starting a new saga if one is already running.
        if Saga.objects.filter(related_resource_id=project.id, status=Saga.SagaStatus.IN_PROGRESS).exists():
            return Response(
                {"detail": "A deletion process for this project is already in progress."},
                status=status.HTTP_409_CONFLICT
            )

        # 2. Soft Delete: Mark the project's status to prevent further use.
        # This is a critical safety step.
        project.status = 'pending_deletion'
        project.save()

        # 3. Create Saga State: Record the start of this distributed transaction in our database.
        saga = Saga.objects.create(
            saga_type='project_deletion',
            related_resource_id=project.id
        )
        
        # Define which services are expected to confirm their part of the cleanup.
        # This list defines the scope of this saga.
        services_to_confirm = ['NodeService', 'MemoryService', 'DataService', 'RAGService', 'GraphService'] # Add 'MemoryService', etc. later
        for service_name in services_to_confirm:
            SagaStep.objects.create(saga=saga, service_name=service_name)
        
        # 4. Publish Event: Tell the rest of the system to start working.
        try:
            event_publisher.publish_project_deletion_initiated(
                project_id=project.id,
                owner_id=project.owner_id
            )
        except Exception as e:
            # If we can't even publish the event, the saga cannot start.
            # We must roll back our local state changes and inform the user.
            project.status = 'active' # Revert the status
            project.save()
            saga.status = Saga.SagaStatus.FAILED # Mark the saga as failed immediately
            saga.save()
            
            # Log the actual error `e` for debugging.
            print(f"ERROR: Failed to publish project.deletion.initiated event: {e}")
            
            return Response(
                {"error": "The deletion process could not be started due to a messaging system error. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 5. Success Response: Inform the user that the process has begun.
        return Response(
            {"message": "Project deletion process has been successfully initiated."},
            status=status.HTTP_202_ACCEPTED
        )