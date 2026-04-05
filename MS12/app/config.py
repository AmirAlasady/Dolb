import os
from dotenv import load_dotenv

load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
DATA_SERVICE_GRPC_URL = os.getenv("DATA_SERVICE_GRPC_URL")
RAG_SERVICE_GRPC_URL = os.getenv("RAG_SERVICE_GRPC_URL")
CHROMA_DB_HOST = os.getenv("CHROMA_DB_HOST")
CHROMA_DB_PORT = int(os.getenv("CHROMA_DB_PORT", 8000))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")