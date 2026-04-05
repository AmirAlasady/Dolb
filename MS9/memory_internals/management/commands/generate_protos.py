# MS9/memory_internals/management/commands/generate_protos.py

import os
import subprocess
import fileinput
import sys
from pathlib import Path
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Generates and fixes Python gRPC code from .proto files for the Memory Service.'
    requires_system_checks = [] # Allows this command to run without a full Django app check

    def handle(self, *args, **options):
        # Define the paths relative to the Django project's base directory
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        proto_path = base_dir / 'memory_internals' / 'protos'
        output_path = base_dir / 'memory_internals' # Generate directly into the app
        
        self.stdout.write(f"Proto source directory: {proto_path}")
        self.stdout.write(f"Generated code output directory: {output_path}")

        if not proto_path.is_dir():
            self.stderr.write(self.style.ERROR(f"Proto path '{proto_path}' does not exist."))
            return

        proto_files = [f for f in proto_path.iterdir() if f.suffix == '.proto']
        if not proto_files:
            self.stdout.write(self.style.WARNING('No .proto files found in protos/ directory.'))
            return
            
        # Command to run the gRPC code generator
        command = [
            sys.executable, '-m', 'grpc_tools.protoc',
            f'--proto_path={proto_path}',
            f'--python_out={output_path}',
            f'--grpc_python_out={output_path}',
        ] + [str(pf) for pf in proto_files]

        self.stdout.write(f"Running command: {' '.join(command)}")
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.stdout.write(self.style.SUCCESS('Successfully generated gRPC Python stubs.'))
        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR('Failed to generate gRPC stubs.'))
            self.stderr.write(e.stderr)
            return

        # Automatically fix the relative imports in the generated _grpc.py file
        for proto_file in proto_files:
            base_name = proto_file.stem
            grpc_file_path = output_path / f'{base_name}_pb2_grpc.py'
            
            self.stdout.write(f"Fixing imports in {grpc_file_path}...")
            with fileinput.FileInput(str(grpc_file_path), inplace=True) as file:
                for line in file:
                    if line.strip() == f'import {base_name}_pb2 as {base_name}__pb2':
                        print(f'from . import {base_name}_pb2 as {base_name}__pb2', end='\n')
                    else:
                        print(line, end='')
            self.stdout.write(self.style.SUCCESS('Imports fixed.'))