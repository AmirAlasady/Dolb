# data_internals/clients.py
import httpx
from django.conf import settings
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

class ProjectServiceClient:
    def authorize_user(self, jwt_token: str, project_id: str):
        headers = {"Authorization": f"Bearer {jwt_token}"}
        url = f"{settings.PROJECT_SERVICE_URL}/ms2/internal/v1/projects/{project_id}/authorize"
        try:
            with httpx.Client() as client:
                response = client.get(url, headers=headers)
                if response.status_code in [403, 404]:
                    raise PermissionDenied("You do not have permission for this project.")
                response.raise_for_status()
        except httpx.RequestError:
            raise ValidationError("Could not connect to the Project Service.")