# MS5/inference_engine/ticket_manager.py
import secrets
import json
from django.conf import settings

def generate_ticket(job_id: str, user_id: str) -> str:
    """
    Generates a secure, one-time ticket and stores it in Redis with a TTL.
    """
    ticket = f"ws_ticket_{secrets.token_urlsafe(32)}"
    ticket_data = {
        "job_id": job_id,
        "user_id": user_id
    }
    
    # Use SETEX to set the key with an expiry of 60 seconds.
    settings.REDIS_CLIENT.setex(
        f"ws_ticket:{ticket}",
        60,
        json.dumps(ticket_data)
    )
    return ticket