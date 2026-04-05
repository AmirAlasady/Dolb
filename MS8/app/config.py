import os
import redis
from dotenv import load_dotenv

load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create a global Redis client instance
redis_client = redis.from_url(REDIS_URL, decode_responses=False)