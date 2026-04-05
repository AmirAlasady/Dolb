import httpx
import os
from django.conf import settings
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from django.core.exceptions import ImproperlyConfigured

class ServiceUnavailable(Exception):
    pass

class BaseServiceClient:
    """
    Base client for handling HTTP communications with other microservices.
    Handles URL configuration and standardized error responses.
    """
    def __init__(self, service_name, setting_key):
        self.service_name = service_name
        self.base_url = getattr(settings, setting_key, None)
        
        if not self.base_url:
            # Fallback to os.getenv just in case it wasn't added to settings.py
            self.base_url = os.getenv(setting_key)
        
        if not self.base_url:
            raise ImproperlyConfigured(f"{setting_key} is not configured in settings or environment.")
            
        self.client = httpx.Client(base_url=self.base_url, timeout=10.0)

    def _handle_response(self, response):
        """
        Maps upstream HTTP status codes to downstream Django Rest Framework exceptions.
        """
        if response.status_code == 204:
            return None # Success, no content
            
        if 200 <= response.status_code < 300:
            return response.json()
            
        error_msg = f"Error from {self.service_name}"
        try:
            data = response.json()
            if isinstance(data, dict):
                error_msg = data.get('detail', data.get('error', error_msg))
        except Exception:
            error_msg = f"{error_msg}: {response.text}"

        if response.status_code == 400:
            raise ValidationError(error_msg)
        elif response.status_code == 401:
            raise PermissionDenied(f"Authentication failed with {self.service_name}")
        elif response.status_code == 403:
            raise PermissionDenied(error_msg)
        elif response.status_code == 404:
            raise NotFound(error_msg)
        elif response.status_code >= 500:
            raise ServiceUnavailable(f"{self.service_name} is currently unavailable (5xx).")
            
        response.raise_for_status()

class ProjectServiceClient(BaseServiceClient):
    """
    Client for the Project Service (MS2).
    Used to verify that the active user has permission to access the Project
    they are trying to build a graph for.
    """
    def __init__(self):
        super().__init__('Project Service', 'PROJECT_SERVICE_URL')

    def check_project_access(self, jwt_token, project_id):
        """
        Calls MS2's internal authorization endpoint.
        Returns None on success (204), raises Exception on failure.
        """
        path = f"/ms2/internal/v1/projects/{project_id}/authorize"
        headers = {"Authorization": f"Bearer {jwt_token}"}
        
        try:
            response = self.client.get(path, headers=headers)
            self._handle_response(response)
        except httpx.RequestError as e:
            raise ServiceUnavailable(f"Failed to connect to Project Service: {str(e)}")

class NodeServiceClient(BaseServiceClient):
    """
    Client for the Node Service (MS4).
    Used to verify that the 'ms4_node_id' provided by the user actually exists
    and belongs to them before we link it to a GNode.
    """
    def __init__(self):
        super().__init__('Node Service', 'NODE_SERVICE_URL')

    def verify_node_existence(self, jwt_token, ms4_node_id):
        """
        Calls MS4 to retrieve node details. If the node doesn't exist or 
        doesn't belong to the user, MS4 will return 404.
        """
        # Using the public API endpoint since we are acting on behalf of the user
        path = f"/ms4/api/v1/nodes/{ms4_node_id}/"
        headers = {"Authorization": f"Bearer {jwt_token}"}

        try:
            response = self.client.get(path, headers=headers)
            return self._handle_response(response)
        except httpx.RequestError as e:
            raise ServiceUnavailable(f"Failed to connect to Node Service: {str(e)}")

    def claim_node(self, jwt_token, ms4_node_id):
        """Tells MS4 to mark this node as used_in_graph=True"""
        path = f"/ms4/internal/v1/nodes/{ms4_node_id}/claim/"
        headers = {"Authorization": f"Bearer {jwt_token}"}
        try:
            response = self.client.post(path, headers=headers)
            self._handle_response(response)
        except httpx.RequestError as e:
            raise ServiceUnavailable(f"Failed to claim node in MS4: {e}")

    def unclaim_node(self, jwt_token, ms4_node_id):
        """Tells MS4 to mark this node as used_in_graph=False"""
        path = f"/ms4/internal/v1/nodes/{ms4_node_id}/unclaim/"
        headers = {"Authorization": f"Bearer {jwt_token}"}
        try:
            # We don't raise strictly here, unclaim is best-effort cleanup
            self.client.post(path, headers=headers)
        except Exception as e:
            print(f"Warning: Failed to unclaim node {ms4_node_id}: {e}")