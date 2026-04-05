import os
from dotenv import load_dotenv

load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
TOOL_SERVICE_GRPC_URL = os.getenv("TOOL_SERVICE_GRPC_URL")
DATA_SERVICE_GRPC_URL = os.getenv("DATA_SERVICE_GRPC_URL")