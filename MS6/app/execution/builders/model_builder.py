# MS6/app/execution/builders/model_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
import json

# Text model imports
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
# Import the required enums for the modern Gemini API
#from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Image model imports (commented out as per your code, but kept for future use)
# import torch
# from diffusers import DiffusionPipeline
from app.execution.custom_lrs_llm import ChatLRS

class ModelBuilder(BaseBuilder):
    """
    Instantiates the correct model pipeline. This definitive version correctly
    parses the nested schema structure for credentials and parameters and uses
    the modern, safe API for Google Gemini.
    """
    
    def _get_value_from_schema(self, schema_block: dict, key: str, value_field: str = 'default') -> any:
        """
        A robust helper to find a key within a nested 'properties' block
        and return the value from a specified field (e.g., 'default').
        """
        properties = schema_block.get("properties", {})
        if key in properties and isinstance(properties[key], dict):
            return properties[key].get(value_field)
        return None

    async def build(self, context: BuildContext) -> BuildContext:
        job = context.job
        model_data = job.model_config
        
        provider = model_data.get("provider")
        # This is the full JSON object from MS3, including the schema and nested values
        # from the user-configured model.
        full_config = model_data.get("configuration", {})
        
        final_params = {**job.default_params, **job.param_overrides}
        
        logger.info(f"[{job.id}] Building model for provider: '{provider}' using definitive schema parser.")
        logger.debug(f"[{job.id}] Full configuration received:\n{json.dumps(full_config, indent=2)}")

        if provider == "google":
            credentials_schema = full_config.get("credentials", {})
            parameters_schema = full_config.get("parameters", {})

            # 1. Extract the API key from the 'default' field of the credentials schema
            api_key = self._get_value_from_schema(credentials_schema, "api_key", value_field='default')
            
            if not api_key:
                raise ValueError("Could not extract 'api_key' from the model configuration's 'credentials.properties.api_key.default' field.")

            # 2. Get model_name, prioritizing user override, then the schema default.
            model_name = final_params.pop("model_name", self._get_value_from_schema(parameters_schema, "model_name"))
            if not model_name:
                raise ValueError("Could not determine 'model_name'.")
            
            # 3. Define the mandatory safety settings for the modern API
            #safety_settings = {
            #    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            #    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            #    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            #    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            #}

            context.llm = ChatGoogleGenerativeAI(
                google_api_key=api_key, 
                model=model_name, 
                #safety_settings=safety_settings,
                **final_params
            )
            logger.info(f"[{job.id}] Successfully built Google Gemini model '{model_name}'.")

        elif provider == "ollama":
            credentials_schema = full_config.get("credentials", {})
            parameters_schema = full_config.get("parameters", {})
            
            base_url = self._get_value_from_schema(credentials_schema, "base_url")
            if not base_url:
                raise ValueError("Could not extract 'base_url' from the Ollama model configuration.")
            
            model_name = final_params.pop("model_name", self._get_value_from_schema(parameters_schema, "model_name"))
            if not model_name:
                raise ValueError("Could not determine 'model_name' for Ollama.")
                
            context.llm = ChatOllama(base_url=base_url, model=model_name, **final_params)
            logger.info(f"[{job.id}] Successfully built Ollama model '{model_name}' on '{base_url}'.")

        elif provider == "lrs":
            # 1. Get the URL of the LRS Inference Gateway from the configuration.
            lrs_url = full_config.get("credentials", {}).get("properties", {}).get("url", {}).get("default")
            if not lrs_url:
                raise ValueError("LRS model configuration is missing the 'url' endpoint.")

            # 2. Get the model_name (e.g., 'TinyLlama/...') from the correct location.
            #    It's inside the 'parameters' block, just like for the Google provider.
            model_name = full_config.get("parameters", {}).get("properties", {}).get("model_name", {}).get("default")
            if not model_name:
                raise ValueError("LRS model configuration is missing the 'model_name'.")
            
            # Remove model_name from the final_params so it's not passed as a model parameter
            final_params.pop("model_name", None)

            # 3. Instantiate our custom ChatLRS class
            context.llm = ChatLRS(
                api_url=lrs_url,
                model_name=model_name,
                **final_params
            )
            logger.info(f"[{job.id}] Successfully built ChatLRS client for model '{model_name}' at '{lrs_url}'.")
        # Your image generation logic is preserved.
        # elif provider == "huggingface_diffusers":
        #    ...
            
        else:
            # Added a check to avoid trying to build an image model as a text model
            if provider != "huggingface_diffusers":
                 raise ValueError(f"Unsupported text model provider: '{provider}'")
        
        logger.info(f"[{job.id}] Model building complete.")
        return context