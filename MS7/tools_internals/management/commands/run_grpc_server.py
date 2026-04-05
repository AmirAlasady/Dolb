import grpc
from concurrent import futures
import time
from django.core.management.base import BaseCommand
import django
import os

# Setup Django before importing models and services
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ms7_project.settings')
django.setup()

from tools_internals.generated import tool_pb2_grpc
from tools_internals.servicer import ToolServicer

class Command(BaseCommand):
    help = 'Starts the gRPC server for the Tool Service'

    def handle(self, *args, **options):
        port = '50057'
        self.stdout.write(f"Starting Tool Service gRPC server on port {port}...")
        
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        
        tool_pb2_grpc.add_ToolServiceServicer_to_server(ToolServicer(), server)
        
        server.add_insecure_port(f'[::]:{port}')
        server.start()
        self.stdout.write(self.style.SUCCESS(f'Tool Service gRPC server started successfully on port {port}.'))
        
        try:
            while True:
                time.sleep(86400) # Sleep for a day
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Stopping gRPC server...'))
            server.stop(0)