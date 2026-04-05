from fastapi import WebSocket
from typing import Dict
from app.logging_config import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages active WebSocket connections, mapping job_ids to WebSocket objects.
    This class is a singleton, ensuring a single state across the application.
    """
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        """Accepts a new connection and maps it to a job_id."""
        await websocket.accept()
        self.active_connections[job_id] = websocket
        logger.info(f"WebSocket connected for job_id: {job_id}. Total connections: {len(self.active_connections)}")

    def disconnect(self, job_id: str):
        """Removes a connection from the manager."""
        if job_id in self.active_connections:
            del self.active_connections[job_id]
            logger.info(f"WebSocket disconnected for job_id: {job_id}. Total connections: {len(self.active_connections)}")

    async def send_message(self, job_id: str, message: dict):
        """Sends a JSON message to a specific client by job_id."""
        websocket = self.active_connections.get(job_id)
        if websocket:
            try:
                await websocket.send_json(message)
                logger.debug(f"Sent message to job_id {job_id}: {str(message)[:100]}...")
            except Exception as e:
                logger.warning(f"Could not send message to job_id {job_id} (client may have disconnected): {e}")
                self.disconnect(job_id)
    
    async def close_connection(self, job_id: str, reason: str = "Job finished"):
        """Closes a specific connection from the server side."""
        websocket = self.active_connections.get(job_id)
        if websocket:
            await websocket.close(code=1000, reason=reason)
            self.disconnect(job_id)

# Create a single global instance of the manager
manager = ConnectionManager()