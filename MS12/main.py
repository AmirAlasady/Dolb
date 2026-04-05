# MS12/main.py
import asyncio
from app.logging_config import setup_logging, logger
from app.messaging.worker import IngestionWorker

def main():
    setup_logging()
    worker_instance = IngestionWorker()
    
    try:
        logger.info("Starting RAG Ingestion Worker (MS12)...")
        asyncio.run(worker_instance.run())
    except KeyboardInterrupt:
        logger.info("Ingestion Worker shutting down gracefully.")
    except Exception as e:
        logger.critical("FATAL: Worker crashed: %s", e, exc_info=True)

if __name__ == "__main__":
    main()