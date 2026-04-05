# MS13/gateway/main.py
import os
import sys
import redis
import httpx
import json
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse

# --- Setup to load Django settings ---
# This allows us to access settings like REDIS_URL from the .env file
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS13.settings')
import django
django.setup()
from django.conf import settings
# --- End of Django setup ---

# Configure logging for the gateway
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS13-Gateway - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="LRS Inference Gateway")
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

# A simple round-robin counter (in-memory, resets on restart, fine for this purpose)
round_robin_counter = {}

@app.post("/ms13/api/v1/infer")
async def handle_inference(request: Request):
    """
    The main inference endpoint called by MS6. It load-balances requests
    to available TGI containers and supports streaming.
    """
    try:
        payload = await request.json()
        model_name = payload.get("model_name")
        stream = payload.get("stream", False)
        
        if not model_name:
            raise HTTPException(status_code=400, detail="Missing 'model_name' in request body.")

        # 1. Get available, healthy endpoints from Redis
        redis_key = f"lrs:model:{model_name}"
        endpoints = list(redis_client.smembers(redis_key))

        if not endpoints:
            logger.error(f"No healthy instances found for model '{model_name}' in Redis.")
            raise HTTPException(status_code=503, detail=f"No healthy inference instances available for model '{model_name}'. Please ask an admin to deploy it.")

        # 2. Select an endpoint using round-robin
        counter_key = f"rr:{model_name}"
        current_index = round_robin_counter.get(counter_key, -1) + 1
        if current_index >= len(endpoints):
            current_index = 0
        round_robin_counter[counter_key] = current_index
        
        target_endpoint = endpoints[current_index]
        
        logger.info(f"Routing request for '{model_name}' to instance: {target_endpoint}")

        # 3. Prepare the request for the TGI container
        tgi_payload = {
            "inputs": payload.get("prompt"),
            "parameters": payload.get("parameters", {}),
            "stream": stream
        }
        
        tgi_url = f"{target_endpoint}/generate_stream" if stream else f"{target_endpoint}/generate"

        # 4. Stream the response back to the client (MS6)
        async def stream_generator():
            try:
                async with httpx.AsyncClient(timeout=900.0) as client:
                    async with client.stream("POST", tgi_url, json=tgi_payload) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes():
                            yield chunk
            except httpx.HTTPStatusError as e:
                error_body = e.response.text
                logger.error(f"Error from TGI container at {target_endpoint}: {e.response.status_code} - {error_body}")
                yield json.dumps({"error": f"Inference failed: {error_body}"}).encode()
            except Exception as e:
                logger.error(f"Streaming failed for model {model_name}: {e}", exc_info=True)
                yield json.dumps({"error": f"An unexpected error occurred during streaming: {str(e)}"}).encode()

        if stream:
            return StreamingResponse(stream_generator(), media_type="application/x-ndjson")
        else:
            # Handle blocking call
            try:
                async with httpx.AsyncClient(timeout=900.0) as client:
                    response = await client.post(tgi_url, json=tgi_payload)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as e:
                error_body = e.response.text
                logger.error(f"Error from TGI container at {target_endpoint}: {e.response.status_code} - {error_body}")
                raise HTTPException(status_code=500, detail=f"Inference failed: {error_body}")

    except Exception as e:
        logger.error(f"Error in handle_inference: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal gateway error occurred: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "ok"}