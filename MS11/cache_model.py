from sentence_transformers import SentenceTransformer
from django.conf import settings
import os

# We need to set the settings module to read the EMBEDDING_MODEL_NAME
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS11.settings')
import django
django.setup()

def main():
    """
    This script's only purpose is to download and cache the
    embedding model from Hugging Face Hub.
    """
    model_name = settings.EMBEDDING_MODEL_NAME
    print(f"--- Starting model caching for: {model_name} ---")
    
    try:
        # This line will trigger the download and save it to your user's
        # .cache/huggingface/hub directory.
        SentenceTransformer(model_name)
        
        print("\n--- SUCCESS ---")
        print(f"Model '{model_name}' has been successfully downloaded and cached.")
        print("You can now start the gRPC server.")
    except Exception as e:
        print(f"\n--- ERROR ---")
        print(f"An error occurred during model caching: {e}")
        print("Please check your internet connection and ensure the model name is correct.")

if __name__ == "__main__":
    main()