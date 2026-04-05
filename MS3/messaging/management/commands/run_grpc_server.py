import grpc
from concurrent import futures
import time
from django.core.management.base import BaseCommand
import django
import os
# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS3.settings')
django.setup()

from aimodelsinternal import model_pb2_grpc
from aimodelsinternal.servicer import ModelServicer


class Command(BaseCommand):
    help = 'Starts the gRPC server for the Model Service'

    def handle(self, *args, **options):
        self.stdout.write("Starting Model Service gRPC server on port 50052...")
        
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        
        # Attach your servicer to the server
        model_pb2_grpc.add_ModelServiceServicer_to_server(ModelServicer(), server)
        
        # Start listening
        server.add_insecure_port('[::]:50052')
        server.start()
        self.stdout.write(self.style.SUCCESS('Model Service gRPC server started successfully.'))
        
        try:
            while True:
                time.sleep(86400) # One day
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Stopping gRPC server...'))
            server.stop(0)
