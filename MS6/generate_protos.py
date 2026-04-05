import os
import subprocess
import fileinput
import sys
from pathlib import Path

def main():
    """Generates and fixes gRPC stubs for the executor."""
    root_dir = Path(__file__).parent
    proto_path = root_dir / 'app' / 'internals' / 'protos'
    output_path = root_dir / 'app' / 'internals' / 'generated'
    
    print(f"Project root directory: {root_dir}")
    print(f"Proto source directory: {proto_path}")
    print(f"Generated code output directory: {output_path}")

    if not proto_path.is_dir():
        print(f"ERROR: Proto path '{proto_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / '__init__.py').touch()

    proto_files = [f for f in proto_path.iterdir() if f.suffix == '.proto']
    if not proto_files:
        print('No .proto files found. Exiting.')
        return
        
    command = [
        sys.executable,  # Use the same python interpreter running the script
        '-m',
        'grpc_tools.protoc',
        f'--proto_path={proto_path}',
        f'--python_out={output_path}',
        f'--grpc_python_out={output_path}',
    ] + [str(pf) for pf in proto_files]

    print(f"Running command: {' '.join(command)}")
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print("ERROR: Failed to generate gRPC stubs.", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        sys.exit(1)

    print('Successfully generated gRPC stubs. Now fixing imports...')
    for proto_file in proto_files:
        base_name = proto_file.stem
        grpc_file_path = output_path / f'{base_name}_pb2_grpc.py'
        
        with fileinput.FileInput(str(grpc_file_path), inplace=True) as file:
            for line in file:
                if line.strip() == f'import {base_name}_pb2 as {base_name}__pb2':
                    print(f'from . import {base_name}_pb2 as {base_name}__pb2', end='\n')
                else:
                    print(line, end='')

    print('Imports fixed successfully.')

if __name__ == '__main__':
    main()