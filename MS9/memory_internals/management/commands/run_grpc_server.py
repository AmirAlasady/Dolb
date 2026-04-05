# MS9/memory_internals/management/commands/run_grpc_server.py

import grpc
from concurrent import futures
import time
import logging
from django.core.management.base import BaseCommand
import django
import os

# Configure logging for the server itself
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS9-gRPC-Server - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure the Django environment is set up before importing models/services
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS9.settings') # <--- CORRECT
django.setup()

from memory_internals import memory_pb2_grpc
from memory_internals.servicer import MemoryServicer

class Command(BaseCommand):
    help = 'Starts the gRPC server for the Memory Service'

    def handle(self, *args, **options):
        grpc_port = '50059'
        logger.info(f"Attempting to start Memory Service gRPC server on port {grpc_port}...")
        
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        
        memory_pb2_grpc.add_MemoryServiceServicer_to_server(MemoryServicer(), server)
        
        server.add_insecure_port(f'[::]:{grpc_port}')
        server.start()
        logger.info(f'Memory Service gRPC server started successfully on port {grpc_port}.')
        
        try:
            # Keep the server running indefinitely
            server.wait_for_termination()
        except KeyboardInterrupt:
            logger.warning('Stopping gRPC server due to user request...')
            server.stop(0)
            logger.info('gRPC server stopped.')