# MS8/main.py

from fastapi import FastAPI
import asyncio
import uvicorn
from app.logging_config import setup_logging, logger # <-- This import now works
from app.server.routes import router as websocket_router
from app.messaging.rabbitmq_consumer import RabbitMQConsumer

# Create the FastAPI app instance BEFORE the startup event
app = FastAPI(title="Real-time Results Service")

@app.on_event("startup")
async def startup_event():
    """On startup, configure logging and create the background consumer task."""
    setup_logging() # Configure the logger
    logger.info("Application startup...")
    consumer = RabbitMQConsumer()
    # Create a background task that will run the consumer loop indefinitely
    asyncio.create_task(consumer.run())
    logger.info("RabbitMQ consumer background task created.")

# Include the WebSocket router
app.include_router(websocket_router)

@app.get("/health", tags=["System"])
def health_check():
    """A simple health check endpoint."""
    return {"status": "ok"}

# This block allows running the server directly with `python main.py`
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8008, reload=True)