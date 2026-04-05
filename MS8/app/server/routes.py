# MS8/app/server/routes.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
import json
from app.server.connection_manager import manager
from app.config import redis_client
from app.logging_config import logger

router = APIRouter()

def validate_and_consume_ticket(ticket: str) -> Optional[dict]:
    """
    Checks Redis for a ticket. If found, it returns the data and
    immediately deletes the ticket to ensure it's single-use.
    """
    redis_key = f"ws_ticket:{ticket}"
    try:
        # Use a pipeline for an atomic GET and DEL operation
        pipe = redis_client.pipeline()
        pipe.get(redis_key)
        pipe.delete(redis_key)
        results = pipe.execute()
        
        ticket_data_str = results[0]

        if ticket_data_str:
            ticket_data = json.loads(ticket_data_str)
            logger.info(f"Ticket validation successful for job_id: {ticket_data.get('job_id')}")
            return ticket_data
        else:
            logger.warning(f"Ticket '{ticket}' not found in Redis.")
            return None
    except Exception as e:
        logger.error(f"Redis error during ticket validation: {e}", exc_info=True)
        return None
    
async def replay_cached_results(websocket: WebSocket, job_id: str):
    """
    Checks Redis for cached results for a job_id and sends them to the client.
    """
    redis_key = f"job:result:{job_id}"
    try:
        # LRANGE 0 -1 gets all elements from the list
        cached_messages = redis_client.lrange(redis_key, 0, -1)
        if not cached_messages:
            logger.info(f"No cached results found for job_id: {job_id}")
            return

        logger.info(f"Found {len(cached_messages)} cached messages for job_id: {job_id}. Replaying now...")
        is_final_message = False
        for msg_bytes in cached_messages:
            msg_data = json.loads(msg_bytes.decode())
            await websocket.send_json(msg_data)
            if msg_data.get("status") in ["success", "error"]:
                is_final_message = True
        
        # If the final message was in the cache, we can close the connection now.
        if is_final_message:
            await manager.close_connection(job_id)

    except Exception as e:
        logger.error(f"Error replaying cached results for job_id {job_id}: {e}", exc_info=True)

@router.websocket("/ws/results/")
async def websocket_endpoint(websocket: WebSocket, ticket: Optional[str] = Query(None)):
    if not ticket:
        await websocket.close(code=4001, reason="Ticket query parameter is required.")
        return

    ticket_data = validate_and_consume_ticket(ticket)
    if not ticket_data:
        await websocket.close(code=4003, reason="Invalid, expired, or already used ticket.")
        return
    
    job_id = ticket_data.get("job_id")
    # user_id = ticket_data.get("user_id") # You can use this for logging or further auth
    
    await manager.connect(websocket, job_id)
    await replay_cached_results(websocket, job_id)
    
    try:
        # Keep the connection alive by listening for messages from the client.
        # This loop will break if the client disconnects.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id)