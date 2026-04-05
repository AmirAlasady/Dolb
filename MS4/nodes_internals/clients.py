# in nodes/clients.py

import httpx
import os
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound, APIException
# A custom exception for when a downstream service is unavailable
class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = 'Service settings unavailable, please try again later.'
    default_code = 'service_unavailable'

class BaseServiceClient:
    def __init__(self, service_name: str, env_var_name: str):
        self.service_name = service_name
        base_url = os.getenv(env_var_name)
        if not base_url:
            raise ImproperlyConfigured(f"{env_var_name} is not set in the environment.")
        self.client = httpx.Client(base_url=base_url, timeout=10.0)

    def _handle_response(self, response: httpx.Response):
        """
        A centralized function to interpret HTTP responses from other services
        and raise appropriate DRF exceptions. This version is robust and can
        handle both dictionary and list-based error responses.
        """
        if 200 <= response.status_code < 300:
            return response.json() if response.content else None
        
        # --- THE FIX IS HERE ---
        try:
            error_data = response.json()
        except Exception:
            # If the response isn't valid JSON, use the reason phrase.
            error_data = response.reason_phrase

        error_message = f"Error from {self.service_name}"
        if isinstance(error_data, dict):
            # Handle standard DRF error format: {"detail": "..."} or {"error": "..."}
            error_message = error_data.get("detail", error_data.get("error", str(error_data)))
        elif isinstance(error_data, list):
            # Handle DRF validation error format: ["Error message."]
            error_message = ". ".join(str(item) for item in error_data)
        elif isinstance(error_data, str):
            error_message = error_data
            
        # Raise the appropriate exception with the formatted message.
        if response.status_code == 403:
            raise PermissionDenied(error_message)
        elif response.status_code == 404:
            raise NotFound(error_message)
        elif response.status_code == 400:
            raise ValidationError(error_message)
        else:
            # For 5xx errors or other unexpected codes.
            response.raise_for_status()


# --- The rest of the client classes (ProjectServiceClient, ModelServiceClient) ---
# --- remain exactly the same. No changes are needed there. ---

class ProjectServiceClient(BaseServiceClient):
    def __init__(self):
        super().__init__("Project Service", "PROJECT_SERVICE_URL")

    def authorize_user(self, jwt_token: str, project_id: str):
        headers = {"Authorization": f"Bearer {jwt_token}",
                   "Host": "localhost"  }
        internal_path = f"/ms2/internal/v1/projects/{project_id}/authorize"
        response = self.client.get(internal_path, headers=headers)
        self._handle_response(response)


class ModelServiceClient(BaseServiceClient):
    def __init__(self):
        super().__init__("Model Service", "MODEL_SERVICE_URL")

    def validate_model(self, jwt_token: str, model_id: str):
        headers = {"Authorization": f"Bearer {jwt_token}",
                   "Host": "localhost"  }
        internal_path = f"/ms3/internal/v1/models/{model_id}/validate"
        response = self.client.get(internal_path, headers=headers)
        self._handle_response(response)

    def get_model_capabilities(self, jwt_token: str, model_id: str) -> list:
        """
        Fetches the capabilities for a given model_id from the Model Service.
        """
        print(f"Fetchinggggg capabilities for model ID: {model_id}")
        headers = {"Authorization": f"Bearer {jwt_token}"}
        internal_path = f"/ms3/internal/v1/models/{model_id}/capabilities/"
        response = self.client.get(internal_path, headers=headers)
        print(f"Response status code: {response.status_code}")
        data = self._handle_response(response) # This will raise exceptions on failure
        return data.get("capabilities", [])


class ToolServiceClient(BaseServiceClient):
    def __init__(self):
        super().__init__("Tool Service", "TOOL_SERVICE_URL")

    def validate_tools(self, jwt_token: str, tool_ids: list[str]):
        """
        Calls the Tool Service's internal validation endpoint to check
        if the user has permission to use the given tool IDs.
        """
        headers = {"Authorization": f"Bearer {jwt_token}"}
        payload = {"tool_ids": tool_ids}
        # The endpoint path must match the one in MS7's internal_urls.py
        internal_path = "/ms7/internal/v1/tools/validate/"
        
        response = self.client.post(internal_path, headers=headers, json=payload)
        
        # The _handle_response method will raise PermissionDenied on 403, etc.
        self._handle_response(response)



class MemoryServiceClient(BaseServiceClient):
    def __init__(self):
        super().__init__("Memory Service", "MEMORY_SERVICE_URL")

    def validate_buckets(self, jwt_token: str, bucket_ids: list[str]):
        """
        Calls the Memory Service's internal validation endpoint to check
        if the user has permission to use the given bucket IDs.
        """
        headers = {"Authorization": f"Bearer {jwt_token}"}
        payload = {"bucket_ids": bucket_ids}
        # This path must match the one in MS9's internal_urls.py
        internal_path = "/ms9/internal/v1/buckets/validate/"
        
        try:
            response = self.client.post(internal_path, headers=headers, json=payload)
            self._handle_response(response) # Will raise exceptions on 4xx/5xx errors
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            # Provide a more specific error if the service is down
            raise ValidationError(f"Could not connect to Memory Service to validate buckets. Error: {e}")


# --- ADD THIS NEW CLIENT CLASS ---
class RAGServiceClient(BaseServiceClient):
    def __init__(self):
        super().__init__("RAG Service", "RAG_SERVICE_URL")

    def validate_collections(self, jwt_token: str, collection_ids: list[str]):
        """
        Calls the RAG Service's internal validation endpoint to check
        if the user has permission to use the given collection IDs.
        """
        if not collection_ids:
            return # Nothing to validate

        headers = {"Authorization": f"Bearer {jwt_token}"}
        payload = {"collection_ids": collection_ids}
        # This path must match the one we will create in MS11's internal_urls.py
        internal_path = "/ms11/internal/v1/collections/validate/"
        
        try:
            response = self.client.post(internal_path, headers=headers, json=payload)
            # The _handle_response method will correctly raise PermissionDenied, NotFound, etc.
            self._handle_response(response)
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            raise ServiceUnavailable(f"Could not connect to RAG Service to validate collections: {e}")











class GraphControlClient:
    """Client to notify MS14 about node lifecycle events."""
    
    def __init__(self):
        self.base_url = os.getenv('GRAPH_CONTROL_URL')
        if not self.base_url:
            # Fallback or log warning
            print("WARNING: GRAPH_CONTROL_URL not set in MS4.")
            self.client = None
        else:
            self.client = httpx.Client(base_url=self.base_url, timeout=5.0)

    def notify_node_deletion(self, node_id: str):
        """
        Tells MS14 that a specific MS4 node is being deleted, 
        so MS14 can remove the reference from any GNodes.
        """
        if not self.client:
            return

        # This endpoint will be created in MS14 Part 2
        url = "/ms14/api/v1/internals/webhook/node-deleted/"
        payload = {"ms4_node_id": node_id}
        
        # We use a system-level call (no user JWT needed for this webhook, 
        # or use a service secret in headers if you implemented service-to-service auth)
        try:
            response = self.client.post(url, json=payload)
            # We don't raise error if MS14 is down, we just want to try best-effort 
            # or force consistency depending on your strictness requirement.
            if response.status_code >= 400:
                print(f"Warning: MS14 returned error during cleanup: {response.text}")
        except Exception as e:
            print(f"Warning: Failed to notify MS14 about node deletion: {e}")