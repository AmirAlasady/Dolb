# MS11/rag_internals/management/commands/run_grpc_server.py

import grpc
from concurrent import futures
import time
import logging
import sys
from django.core.management.base import BaseCommand
import django
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS11-gRPC-Server - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS11.settings')
django.setup()

from rag_internals import rag_pb2_grpc
from rag_internals.servicer import RAGServicer

class Command(BaseCommand):
    help = 'Starts the gRPC server for the RAG Service'

    def handle(self, *args, **options):
        grpc_port = '50060'
        logger.info(f"Attempting to start RAG Service gRPC server on port {grpc_port}...")
        
        try:
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
            
            # --- THE FIX IS HERE: REGISTER BOTH SERVICES ---
            servicer_instance = RAGServicer()
            # Register the public-facing service for MS5
            rag_pb2_grpc.add_RAGServiceServicer_to_server(servicer_instance, server)
            # Register the internal service for MS12
            rag_pb2_grpc.add_RAGInternalServiceServicer_to_server(servicer_instance, server)
            # --- END OF FIX ---
            
            server.add_insecure_port(f'[::]:{grpc_port}')
            server.start()
            logger.info(f'RAG Service gRPC server started successfully on port {grpc_port}, serving both RAGService and RAGInternalService.')
            
            server.wait_for_termination()

        except RuntimeError as e:
            logger.critical(f"FATAL: Could not start gRPC server. {e}", exc_info=True)
            sys.exit(1)
        except KeyboardInterrupt:
            logger.warning('Stopping gRPC server due to user request (CTRL+C)...')
            server.stop(0)
            logger.info('gRPC server stopped.')