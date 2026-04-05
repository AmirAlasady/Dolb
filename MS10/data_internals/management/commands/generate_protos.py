# data_internals/management/commands/generate_protos.py
import os, subprocess, fileinput, sys
from pathlib import Path
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Generates and fixes Python gRPC code from .proto files.'
    requires_system_checks = []

    def handle(self, *args, **options):
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        proto_path = base_dir / 'data_internals' / 'protos'
        output_path = base_dir / 'data_internals'
        
        self.stdout.write(f"Proto source: {proto_path}")
        self.stdout.write(f"Output path: {output_path}")

        proto_files = [f for f in proto_path.iterdir() if f.suffix == '.proto']
        if not proto_files:
            self.stdout.write(self.style.WARNING('No .proto files found.'))
            return
            
        command = [sys.executable, '-m', 'grpc_tools.protoc', f'--proto_path={proto_path}', f'--python_out={output_path}', f'--grpc_python_out={output_path}'] + [str(pf) for pf in proto_files]
        
        try:
            subprocess.run(command, check=True)
            self.stdout.write(self.style.SUCCESS('Successfully generated stubs.'))
        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR(f'Failed to generate stubs: {e}'))
            return

        for proto_file in proto_files:
            base_name = proto_file.stem
            grpc_file_path = output_path / f'{base_name}_pb2_grpc.py'
            with fileinput.FileInput(str(grpc_file_path), inplace=True) as file:
                for line in file:
                    if line.strip() == f'import {base_name}_pb2 as {base_name}__pb2':
                        print(f'from . import {base_name}_pb2 as {base_name}__pb2', end='\n')
                    else:
                        print(line, end='')
        self.stdout.write(self.style.SUCCESS('Imports fixed.'))