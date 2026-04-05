# in aimodels/services.py (Corrected and Final Version)

from django.db.models import Q
from .models import AIModel
from rest_framework.exceptions import ValidationError, PermissionDenied
import jsonschema

# --- Placeholder Encryption (as before) ---
def encrypt_values(raw_values: dict, schema: dict) -> dict:
    encrypted = {}
    for key, value in raw_values.items():
        if schema.get('properties', {}).get(key, {}).get('sensitive'):
            encrypted[key] = f"ENCRYPTED({value[::-1]})"
        else:
            encrypted[key] = value
    return encrypted

# --- The Final Service Class ---
class AIModelService:
    def get_available_models_for_user(self, user_id):
        """ Returns all system models + the user's own private models. """
        return AIModel.objects.filter(
            Q(is_system_model=True) | Q(owner_id=user_id)
        )

    def get_model_by_id(self, model_id, user_id):
        """
        Retrieves a single model, ensuring the user has permission to view it.
        (A user can view any system model or their own models).
        """
        try:
            model = AIModel.objects.get(id=model_id)
        except AIModel.DoesNotExist:
            raise ValidationError("Model not found.") # This will result in a 404/400

        # --- THE CRITICAL FIX IS HERE ---
        # If it's a system model, anyone can view it.
        # If it's NOT a system model, the owner_id MUST match the user_id.
        is_owner = str(model.owner_id) == str(user_id)
        
        if not model.is_system_model and not is_owner:
            raise PermissionDenied("You do not have permission to access this model.")
            
        return model


    """
    def create_user_model(self, *, owner_id, name, provider, configuration):
        #Creates a new private model configuration for a user. 
        # (This method was already correct, but we include it for completeness)
        try:
            blueprint = AIModel.objects.get(provider=provider, is_system_model=True)
        except AIModel.DoesNotExist:
            raise ValidationError(f"No system model template found for provider '{provider}'.")
            
        schema = blueprint.configuration
        try:
            jsonschema.validate(instance=configuration, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValidationError(f"Configuration is invalid for '{provider}': {e.message}")
            
        encrypted_config = encrypt_values(configuration, schema)
        
        user_model = AIModel.objects.create(
            is_system_model=False,
            owner_id=owner_id,
            name=name,
            provider=provider,
            configuration=encrypted_config,
            capabilities=blueprint.capabilities
        )
        return user_model
    """


    """
    def update_user_model(self, *, model_id, user_id, name, configuration, capabilities=None):

        # Step 1: Get the model (this also performs permission checks)
        model_to_update = self.get_model_by_id(model_id, user_id)
        
        if model_to_update.is_system_model and self.request.user.is_staff is False:
            raise PermissionDenied("System models cannot be modified.")
            
        # Step 2: Validate the configuration against the blueprint (unchanged)
        blueprint = AIModel.objects.get(provider=model_to_update.provider, is_system_model=True)
        schema = blueprint.configuration
        try:
            jsonschema.validate(instance=configuration, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValidationError(f"Configuration is invalid: {e.message}")
            
        # Step 3: Update the model's fields
        model_to_update.name = name
        model_to_update.configuration = encrypt_values(configuration, schema) # Placeholder encryption
        
        # --- THE CHANGE IS HERE ---
        # If the 'capabilities' argument was passed, update that field as well.
        if capabilities is not None:
            model_to_update.capabilities = capabilities
        # --- END OF CHANGE ---
            
        model_to_update.save()
        return model_to_update
    """

    def create_user_model(self, *, owner_id, name, provider, model_name, credentials, parameters):
        """
        Creates a new private model. It prepares the simple config for the
        model's save() method to process.
        """
        # Prepare the simple configuration dictionary
        simple_config = {
            "model_name": model_name,
            "credentials": credentials,
            "parameters": parameters
        }
        
        # Create the unsaved instance. The magic happens in the .save() method.
        user_model = AIModel(
            is_system_model=False,
            owner_id=owner_id,
            name=name,
            provider=provider,
            configuration=simple_config
        )
        # When we call save(), our custom logic will run and build the complex schema.
        user_model.save()
        return user_model
    
    # The request payload to the API will now be structured, just like the create method.
    # It will send name, credentials, and parameters.
    def update_user_model(self, *, model_id, user_id, name, credentials, parameters):
        """
        Updates a user's private model configuration by reconstructing its
        backward-compatible schema. This ensures consistency and validity.
        """
        model_to_update = self.get_model_by_id(model_id, user_id)
        
        if model_to_update.is_system_model:
            # Assuming you have a way to check if the user is staff in your view
            raise PermissionDenied("System models cannot be modified by standard users.")
        
        # --- RECONSTRUCTION LOGIC ---
        
        # The 'configuration' on an existing model is the complex/old format.
        # We need to extract the original, immutable model_name from it.
        try:
            original_model_name = model_to_update.configuration["parameters"]["properties"]["model_name"]["default"]
        except KeyError:
             raise ValidationError("Cannot update model: The original 'model_name' could not be determined from its existing configuration.")

        # Prepare the simple configuration dictionary with the new user data,
        # but preserving the original model_name.
        simple_config = {
            "model_name": original_model_name, # This CANNOT be changed
            "credentials": credentials,
            "parameters": parameters
        }

        # Update the name and temporarily set the configuration to the simple format.
        model_to_update.name = name
        model_to_update.configuration = simple_config
        # Clear capabilities so the save() method logic is forced to re-populate them.
        model_to_update.capabilities = [] 
        
        # When we call save(), our custom model logic will run again. It will detect
        # the simple format, use it to rebuild the full complex schema, and populate
        # the correct capabilities, ensuring the model is always valid.
        model_to_update.save()
        
        return model_to_update
    
    def delete_user_model(self, *, model_id, user_id):
        """ Deletes a user's private model configuration. """
        model_to_delete = self.get_model_by_id(model_id, user_id)
        
        if model_to_delete.is_system_model:
             raise PermissionDenied("System models cannot be deleted.")
             
        model_to_delete.delete()
        # No return value needed for a successful delete.