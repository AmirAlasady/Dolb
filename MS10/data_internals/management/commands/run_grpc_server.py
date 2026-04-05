import grpc
from concurrent import futures
import time
from django.core.management.base import BaseCommand
import django
import os

# Setup Django before importing models and services
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS10.settings')
django.setup()

from data_internals import data_pb2_grpc
from data_internals.servicer import DataServicer

class Command(BaseCommand):
    help = 'Starts the gRPC server for the Data Service'

    def handle(self, *args, **options):
        port = '50058'
        self.stdout.write(f"Starting Data Service gRPC server on port {port}...")
        
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        
        data_pb2_grpc.add_DataServiceServicer_to_server(DataServicer(), server)
        
        server.add_insecure_port(f'[::]:{port}')
        server.start()
        self.stdout.write(self.style.SUCCESS(f'Data Service gRPC server started successfully on port {port}.'))
        
        try:
            while True:
                time.sleep(86400) # Sleep for a day
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Stopping gRPC server...'))
            server.stop(0)
