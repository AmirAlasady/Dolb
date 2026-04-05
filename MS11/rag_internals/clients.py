# rag_internals/clients.py

import httpx
from django.conf import settings
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

# A custom exception for when a downstream service is unavailable
class ServiceUnavailable(Exception):
    pass

class ProjectServiceClient:
    """
    Client for making secure, internal REST API calls to the Project Service (MS2)
    to validate project ownership.
    """
    def authorize_user(self, jwt_token: str, project_id: str):
        headers = {"Authorization": f"Bearer {jwt_token}"}
        url = f"{settings.PROJECT_SERVICE_URL}/ms2/internal/v1/projects/{project_id}/authorize"
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers)

                if response.status_code == 204:
                    # 204 No Content is the success signal from MS2.
                    return
                elif response.status_code == 404:
                    raise NotFound("The specified project does not exist.")
                elif response.status_code == 403:
                    raise PermissionDenied("You do not have permission to access this project.")
                else:
                    # For any other server-side error from MS2.
                    response.raise_for_status()
        except httpx.RequestError as exc:
            raise ServiceUnavailable(f"Could not connect to the Project Service: {exc}")