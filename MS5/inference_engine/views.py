# MS5/inference_engine/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError

from .serializers import InferenceRequestSerializer
from .services import InferenceOrchestrationService

from messaging.event_publisher import inference_job_publisher 
from django.conf import settings



class InferenceAPIView(APIView):
    """
    The single entry point for initiating an inference job on a configured node.
    It delegates all complex logic to the InferenceOrchestrationService.
    
    Endpoint: POST /ms5/api/v1/nodes/{node_id}/infer/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, node_id):
        """
        Handles the submission of a new inference job.
        
        1. Validates the user's incoming query data.
        2. Passes the request to the service layer for orchestration.
        3. Catches any exceptions (e.g., for invalid nodes, permission issues)
           and formats them into a user-friendly error response.
        """
        # Step 1: Validate the request body (e.g., ensure 'prompt' is present)
        serializer = InferenceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = InferenceOrchestrationService()
        try:
            jwt_token = str(request.auth)
            # Step 2: Delegate the core logic to the service layer
            result = service.process_inference_request(
                node_id=str(node_id),
                user_id=str(request.user.id),
                query_data=serializer.validated_data,
                jwt_token=jwt_token #
            )

            # Store a temporary mapping of job_id -> user_id in Redis for authorization during cancellation
            job_id = result.get("job_id")
            user_id = str(request.user.id)
            if job_id:
                job_owner_key = f"job:owner:{job_id}"
                # Set with a 24-hour expiry. Adjust as needed for max job lifetime.
                settings.REDIS_CLIENT.set(job_owner_key, user_id, ex=86400)

            # Step 3: Return a success response indicating the job was submitted
            return Response(result, status=status.HTTP_202_ACCEPTED)
        
        # Step 4: Handle specific, known errors gracefully
        except FileNotFoundError as e:
            # This is typically raised by a gRPC client if a resource (node, model, tool) is not found.
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
            
        except PermissionDenied as e:
            # This can be raised by a gRPC client OR by our own service layer
            # (e.g., if the node status is 'inactive' or 'draft').
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
            
        except ValidationError as e:
            # Catches validation errors from other services.
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            # Catch-all for any other unexpected server errors
            print(f"CRITICAL: Unexpected error in inference orchestration for node {node_id}: {e}")
            return Response(
                {"error": "An unexpected server error occurred during job orchestration."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class JobCancellationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, job_id):
        requesting_user_id = str(request.user.id)
        job_id_str = str(job_id)

        # --- AUTHORIZATION LOGIC ---
        job_owner_key = f"job:owner:{job_id_str}"
        stored_owner_id = settings.REDIS_CLIENT.get(job_owner_key)

        if not stored_owner_id:
            # Job is either complete, never existed, or expired.
            # From a security perspective, we treat it as "not found".
            return Response({"error": "Job not found or has already completed."}, status=status.HTTP_404_NOT_FOUND)

        if stored_owner_id != requesting_user_id:
            # The user making the request is NOT the user who started the job.
            return Response({"error": "You do not have permission to cancel this job."}, status=status.HTTP_403_FORBIDDEN)
        # --- END OF AUTHORIZATION LOGIC ---

        try:
            inference_job_publisher.publish_cancellation_request(job_id_str, requesting_user_id)
            # Once cancellation is requested, we can remove the ownership key.
            settings.REDIS_CLIENT.delete(job_owner_key)
            return Response({"message": "Job cancellation request has been broadcast."}, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            print(f"CRITICAL: Could not publish cancellation event for job {job_id_str}: {e}")
            return Response({"error": "Could not send cancellation signal due to a messaging system error."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)