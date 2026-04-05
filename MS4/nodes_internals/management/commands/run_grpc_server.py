import grpc
from concurrent import futures
import time
from django.core.management.base import BaseCommand
import django
import os

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS4.settings')
django.setup()

from nodes_internals.generated import node_pb2_grpc
from nodes_internals.servicer import NodeServicer

class Command(BaseCommand):
    help = 'Starts the gRPC server for the Node Service'

    def handle(self, *args, **options):
        self.stdout.write("Starting Node Service gRPC server on port 50051...")
        
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        
        # Attach your servicer to the server
        node_pb2_grpc.add_NodeServiceServicer_to_server(NodeServicer(), server)
        
        # Start listening
        server.add_insecure_port('[::]:50051')
        server.start()
        self.stdout.write(self.style.SUCCESS('Node Service gRPC server started successfully.'))
        
        try:
            while True:
                time.sleep(86400) # One day
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Stopping gRPC server...'))
            server.stop(0)