import os
import subprocess
import fileinput
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Generates Python gRPC code from .proto files for the Node Service.'

    def handle(self, *args, **options):
        proto_path = 'nodes/protos'
        output_path = 'nodes'
        
        # ... (Identical logic to the MS3 version) ...
        proto_files = [f for f in os.listdir(proto_path) if f.endswith('.proto')]
        command = [
            'python', '-m', 'grpc_tools.protoc',
            f'--proto_path={proto_path}',
            f'--python_out={output_path}',
            f'--grpc_python_out={output_path}',
        ] + proto_files

        subprocess.run(command, check=True)
        self.stdout.write(self.style.SUCCESS('Successfully generated gRPC Python stubs for Node Service.'))
        
        # --- THE FIX IS HERE ---
        for proto_file in proto_files:
            base_name = proto_file.replace('.proto', '')
            grpc_file_path = os.path.join(output_path, f'{base_name}_pb2_grpc.py')
            
            self.stdout.write(f"Fixing imports in {grpc_file_path}...")
            with fileinput.FileInput(grpc_file_path, inplace=True) as file:
                for line in file:
                    if line.strip() == f'import {base_name}_pb2 as {base_name}__pb2':
                        print(f'from . import {base_name}_pb2 as {base_name}__pb2')
                    else:
                        print(line, end='')
            self.stdout.write(self.style.SUCCESS('Imports fixed.'))
        # --- END OF FIX ---