import os
import subprocess
import fileinput
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Generates Python gRPC code from .proto files.'
    requires_system_checks = [] # Prevents Django app checks from running

    def handle(self, *args, **options):
        proto_path = 'tools_internals/protos'
        output_path = 'tools_internals/generated'
        
        if not os.path.exists(proto_path):
            self.stderr.write(self.style.ERROR(f"Proto path '{proto_path}' does not exist."))
            return
        
        os.makedirs(output_path, exist_ok=True)
        open(os.path.join(output_path, '__init__.py'), 'a').close()

        proto_files = [f for f in os.listdir(proto_path) if f.endswith('.proto')]
        if not proto_files:
            self.stdout.write(self.style.WARNING('No .proto files found.'))
            return
            
        command = [
            'python', '-m', 'grpc_tools.protoc',
            f'--proto_path={proto_path}',
            f'--python_out={output_path}',
            f'--grpc_python_out={output_path}',
        ] + proto_files

        self.stdout.write(f"Running command: {' '.join(command)}")
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.stdout.write(self.style.SUCCESS('Successfully generated gRPC Python stubs.'))
            
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
        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR(f'Failed to generate gRPC stubs: {e.stderr}'))