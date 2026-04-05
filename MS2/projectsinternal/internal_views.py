from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from project.models import Project


class ProjectAuthorizationView(APIView):
    """
    Internal-only view to check if a user is the owner of a project.
    It expects the JWT of the original user to be forwarded in the Authorization header.
    """
    # This view is still protected by authentication. It verifies the forwarded JWT.
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        """
        Checks ownership. Returns 204 on success, 403/404 on failure.
        """
        try:
            # We only need to check for existence and ownership.
            # We can do this with a single, efficient query.
            is_owner = Project.objects.filter(
                id=project_id, 
                owner_id=request.user.id
            ).exists()

            if is_owner:
                # 204 No Content is a lightweight, fast success response.
                # It signals "Yes, authorized" without needing a body.
                return Response(status=status.HTTP_204_NO_CONTENT)
            else:
                # We need to distinguish between "project exists but you don't own it"
                # and "project doesn't exist at all".
                if Project.objects.filter(id=project_id).exists():
                    # The project exists, but the owner_id doesn't match.
                    return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
                else:
                    # The project itself was not found.
                    return Response({"detail": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception:
            # Catch any unexpected errors (e.g., invalid UUID format).
            return Response({"detail": "Bad Request."}, status=status.HTTP_400_BAD_REQUEST)