# MS6/main.py

import asyncio
from app.logging_config import setup_logging, logger
from app.messaging.worker import RabbitMQWorker
from app.messaging.cancellation_listener import CancellationListener

def main():
    """
    The main entry point for the Inference Executor (MS6) application.
    It launches the main worker and the cancellation listener in parallel.
    """
    setup_logging() # Configure the logger first
    worker_instance = RabbitMQWorker()
    cancellation_listener = CancellationListener()

    async def run_all():
        """A wrapper to run multiple asyncio tasks concurrently."""
        # Create tasks for both workers so they can run indefinitely
        worker_task = asyncio.create_task(worker_instance.run())
        listener_task = asyncio.create_task(cancellation_listener.run())
        
        logger.info("Inference Executor Worker and Cancellation Listener are now running.")
        
        # This will run until one of the tasks finishes or is cancelled.
        await asyncio.gather(worker_task, listener_task)

    try:
        logger.info("Starting all MS6 services...")
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("Services shutting down gracefully due to user request (CTRL+C).")
    except Exception as e:
        logger.critical(f"FATAL: A service crashed during startup: {e}", exc_info=True)

if __name__ == "__main__":
    main()