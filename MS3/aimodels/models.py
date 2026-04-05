import uuid
from django.db import models


# --- ADD THIS IMPORT AT THE TOP ---
 # Assuming ProviderSchema is in its own file or update the import path
import logging


import json

import copy

from django.core.exceptions import ValidationError

class ProviderSchema(models.Model):
    """
    The 'Factory Template'. Stores the master rules for a provider and its
    family of models (blueprints). Managed only by admins.
    """
    provider_id = models.CharField(primary_key=True, max_length=100)
    display_name = models.CharField(max_length=255)
    credentials_schema = models.JSONField(default=dict, help_text="The full JSON Schema for credentials, including nested properties.")
    model_blueprints = models.JSONField(default=list, help_text="A JSON array of all model blueprints this provider offers.")

    def __str__(self):
        return self.display_name
    
    
class AIModel(models.Model):
    """
    A single, unified model representing an AI model configuration.
    Can be a global 'System Model' (template) or a private 'User Model'.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    is_system_model = models.BooleanField(
        default=False, 
        db_index=True,
        help_text="True if this is a global model template managed by an admin."
    )
    
    owner_id = models.UUIDField(
        db_index=True, 
        null=True, # A system model has no owner.
        blank=True,
        help_text="The user who owns this configuration. NULL for system models."
    )
    
    name = models.CharField(
        max_length=255, 
        help_text="User-friendly name (e.g., 'My Personal GPT-4o' or 'System Llama 3')."
    )
    
    provider = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Provider identifier (e.g., 'openai', 'ollama', 'anthropic')."
    )
    
    configuration = models.JSONField(
        default=dict,
        help_text="For system models: the JSON schema. For user models: the encrypted config values."
    )
    
    capabilities = models.JSONField(
        default=list, 
        help_text="List of capabilities (e.g., ['text', 'vision', 'tool_use'])."
    )
    
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """
        The 'Assembly Line'. Overrides the default save to construct the
        final, backward-compatible configuration if it doesn't already exist
        in the complex format.
        """
        # This check determines if the configuration is in the NEW simple format
        # or the OLD complex format. We only run the logic if it's the simple one.
        is_simple_format = "schema_version" not in self.configuration

        if is_simple_format:
            logging.info(f"Simple config format detected for '{self.name}'. Building complex schema...")
            try:
                # Extract simple inputs provided by the user/admin
                simple_config = self.configuration
                model_name = simple_config.get("model_name")
                user_credentials = simple_config.get("credentials", {})
                user_parameters = simple_config.get("parameters", {})

                if not (self.provider and model_name):
                    raise ValidationError("Provider and model_name are required to build configuration.")

                # Find the 'Factory Template'
                provider_schema = ProviderSchema.objects.get(provider_id=self.provider)
                blueprint = next(
                    (bp for bp in provider_schema.model_blueprints if bp.get('model_name') == model_name), None
                )
                if not blueprint:
                    raise ValidationError(f"Blueprint for '{model_name}' not found in provider '{self.provider}'.")

                # --- Assemble the complex, old-style configuration ---

                # 1. Start with deep copies to avoid modifying the templates
                final_credentials = copy.deepcopy(provider_schema.credentials_schema)
                final_parameters = copy.deepcopy(blueprint.get("parameters_schema", {}))

                # 2. Inject user-provided credentials into the 'default' field
                for key, value in user_credentials.items():
                    if key in final_credentials.get("properties", {}):
                        final_credentials["properties"][key]["default"] = value

                # 3. Inject user-provided parameters into the 'default' field
                for key, value in user_parameters.items():
                    if key in final_parameters.get("properties", {}):
                        final_parameters["properties"][key]["default"] = value
                
                # 4. Always ensure the model_name is present in the final parameter schema
                final_parameters.setdefault("properties", {})["model_name"] = {
                    "type": "string", "description": "model name", "default": model_name
                }
                
                # 5. Replace the simple config with the fully constructed complex one
                self.configuration = {
                    "schema_version": "1.0",
                    "credentials": final_credentials,
                    "parameters": final_parameters
                }
                
                # 6. Set the capabilities from the blueprint
                self.capabilities = blueprint.get("capabilities", [])
                
                logging.info(f"Successfully constructed backward-compatible config for '{self.name}'.")

            except ProviderSchema.DoesNotExist:
                logging.error(f"FATAL: ProviderSchema for '{self.provider}' not found. Cannot save model.")
                # We raise a validation error to prevent saving a broken model
                raise ValidationError(f"ProviderSchema for '{self.provider}' has not been configured by an admin.")
            except Exception as e:
                logging.error(f"Error constructing AIModel configuration for '{self.name}': {e}", exc_info=True)
                raise ValidationError(f"An unexpected error occurred during configuration construction: {e}")

        # Call the original save method to write to the database
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-is_system_model', 'provider', 'name']
        constraints = [models.UniqueConstraint(fields=['owner_id', 'name'], name='unique_user_model_name')]
        verbose_name = "AI Model Configuration"

    def __str__(self):
        model_type = 'System' if self.is_system_model else f"User ({self.owner_id})"
        return f"{self.name} [{self.provider}] ({model_type})"