# MS12/generate_protos.py

import os
import subprocess
import fileinput
import sys
from pathlib import Path

def main():
    """
    Generates and fixes Python gRPC stubs for the MS12 service.
    This script is the equivalent of the `manage.py generate_protos` command
    for this non-Django application.
    """
    # Use pathlib for robust path handling
    project_root = Path(__file__).parent.resolve()
    proto_path = project_root / 'app' / 'internals' / 'protos'
    output_path = project_root / 'app' / 'internals' / 'generated'
    
    print("--- RAG Ingestion Worker (MS12) Proto Generator ---")
    print(f"Project Root: {project_root}")
    print(f"Proto Source Directory: {proto_path}")
    print(f"Generated Code Output Directory: {output_path}")
    print("-" * 50)

    if not proto_path.is_dir():
        print(f"[ERROR] Proto path '{proto_path}' does not exist. Aborting.", file=sys.stderr)
        sys.exit(1)

    # Ensure the output directory and its __init__.py file exist
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / '__init__.py').touch()

    proto_files = [f for f in proto_path.iterdir() if f.suffix == '.proto']
    if not proto_files:
        print('[WARNING] No .proto files found in protos/ directory. Nothing to do.')
        return
        
    # Construct the command to run the gRPC code generator
    command = [
        sys.executable,  # Use the same python interpreter running this script
        '-m',
        'grpc_tools.protoc',
        f'--proto_path={proto_path}',
        f'--python_out={output_path}',
        f'--grpc_python_out={output_path}',
    ] + [str(pf) for pf in proto_files]

    print(f"Running command: {' '.join(command)}")
    try:
        # We capture stdout/stderr to provide better error messages
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        if result.stderr:
            print(f"[COMPILER WARNINGS]:\n{result.stderr}")
    except subprocess.CalledProcessError as e:
        print("[ERROR] Failed to generate gRPC stubs.", file=sys.stderr)
        print(f"Return Code: {e.returncode}", file=sys.stderr)
        print(f"\n--- STDOUT ---\n{e.stdout}", file=sys.stderr)
        print(f"\n--- STDERR ---\n{e.stderr}", file=sys.stderr)
        sys.exit(1)

    print('\nSuccessfully generated gRPC stubs. Now fixing imports...')
    for proto_file in proto_files:
        base_name = proto_file.stem
        grpc_file_path = output_path / f'{base_name}_pb2_grpc.py'
        
        print(f"Fixing imports in {grpc_file_path}...")
        with fileinput.FileInput(str(grpc_file_path), inplace=True, encoding='utf-8') as file:
            for line in file:
                # This regex is slightly more robust than a simple string match
                import_line = f'import {base_name}_pb2 as {base_name}__pb2'
                if line.strip() == import_line:
                    # Replace with a relative import
                    print(f'from . import {base_name}_pb2 as {base_name}__pb2', end='\n')
                else:
                    print(line, end='')
    
    print('Imports fixed successfully.')
    print("-" * 50)
    print("Proto generation complete.")

if __name__ == '__main__':
    main()