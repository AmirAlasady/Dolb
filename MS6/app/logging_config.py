# MS6/app/logging_config.py

import logging
import sys

# --- THE DEFINITIVE FIX ---
# 1. Define the logger at the module level so it can be imported.
logger = logging.getLogger("MS6-Executor")
# --- END OF FIX ---

def setup_logging():
    """
    Configures the root logger for the application.
    This function should be called ONLY ONCE at startup in main.py.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
        stream=sys.stdout,
    )
    # Silence noisy libraries
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)