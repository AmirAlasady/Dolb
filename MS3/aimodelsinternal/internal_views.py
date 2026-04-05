from rest_framework.permissions import AllowAny # <-- Add this import

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from aimodels.services import AIModelService # Use our existing service layer!

class ModelValidationView(APIView):
    """
    Internal-only view for other services to validate if a user can
    access a specific model.
    """
    permission_classes = [permissions.IsAuthenticated]
    service = AIModelService()

    def get(self, request, model_id):
        """
        Uses the service layer's get method, which already contains
        all the necessary permission logic.
        """
        try:
            print(f"Validating access for model_id: {model_id} for user: {request.user.id}")
            # This method will raise PermissionDenied or ValidationError (NotFound)
            # if the user can't access the model.
            self.service.get_model_by_id(model_id=model_id, user_id=request.user.id)
            print(f"Access validated for model_id: {model_id} for user: {request.user.id}")
            # If it doesn't raise an exception, the user is authorized.
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        except Exception as e:
            print(f"Access validation failed for model_id: {model_id} for user: {request.user.id}")
            # Let DRF's exception handler format the response (403, 404, etc.)
            raise e


        



class ModelCapabilitiesView(APIView):
    """
    Internal-only view for other services to quickly fetch the capabilities
    of a model after validating user access.
    """
    permission_classes = [permissions.IsAuthenticated]
    service = AIModelService()

    def get(self, request, model_id):
        try:
            # The service method already validates that the user can access this model
            model = self.service.get_model_by_id(model_id=model_id, user_id=request.user.id)
            
            # Return only the capabilities list
            return Response({"capabilities": model.capabilities}, status=status.HTTP_200_OK)

        except Exception as e:
            # Let DRF's default exception handler format the 403, 404, etc.
            raise e
        


from aimodels.models import ProviderSchema

# ... (all your existing views like AIModelListCreateAPIView are unchanged)


# --- ADD THIS NEW VIEW AT THE END OF THE FILE ---
class InternalBlueprintDetailView(APIView):
    """
    An internal, unauthenticated endpoint for other services (like MS13) to fetch
    a specific model blueprint from a provider schema.
    """
    permission_classes = [AllowAny] # In production, this would be a shared secret permission

    def get(self, request, *args, **kwargs):
        provider_id = request.query_params.get('provider')
        model_name = request.query_params.get('model_name')

        if not provider_id or not model_name:
            return Response(
                {"error": "Both 'provider' and 'model_name' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            provider_schema = ProviderSchema.objects.get(provider_id=provider_id)
            blueprint = next(
                (bp for bp in provider_schema.model_blueprints if bp.get('model_name') == model_name),
                None
            )
            
            if not blueprint:
                return Response(
                    {"error": f"Blueprint for model '{model_name}' not found in provider '{provider_id}'."},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            return Response(blueprint)

        except ProviderSchema.DoesNotExist:
            return Response(
                {"error": f"ProviderSchema for '{provider_id}' not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"An internal error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )