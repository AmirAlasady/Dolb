# aimodelsinternal/management/commands/run_grpc_server.py
import os
import time
import socket
import grpc
from concurrent import futures
from django.core.management.base import BaseCommand
import django

# Setup Django environment if needed (should already be set by manage.py)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS3.settings')
django.setup()

from aimodelsinternal import model_pb2_grpc
from aimodelsinternal.servicer import ModelServicer

DEFAULT_PORT = 50052
BIND_TRIES = [
    "127.0.0.1",   # prefer localhost IPv4
    "0.0.0.0",     # all IPv4 addresses
    "[::1]",       # IPv6 loopback
    "[::]"         # all IPv6 addresses as last resort
]


def is_port_free(host: str, port: int) -> bool:
    """Quick check whether (host,port) is free from a local TCP perspective."""
    try:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            return s.connect_ex((host.strip("[]"), port)) != 0
    except Exception:
        # If check fails assume not free (safer)
        return False


class Command(BaseCommand):
    help = 'Starts the gRPC server for the Model Service'

    def handle(self, *args, **options):
        self.stdout.write("Starting Model Service gRPC server on port %d..." % DEFAULT_PORT)

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        model_pb2_grpc.add_ModelServiceServicer_to_server(ModelServicer(), server)

        bound = False
        last_exc = None

        for host in BIND_TRIES:
            addr = f"{host}:{DEFAULT_PORT}"
            # Quick local check: if host is IP like 127.0.0.1 or 0.0.0.0 we still try; but if port evidently in use skip
            if not is_port_free(host, DEFAULT_PORT):
                self.stdout.write(self.style.WARNING(f"Port {DEFAULT_PORT} seems in use for host {host}. Trying next host..."))
                continue
            try:
                # wrap add_insecure_port in try so we can handle validate_port_binding_result RuntimeError
                self.stdout.write(f"Attempting to bind gRPC to {addr} ...")
                server.add_insecure_port(addr)
                server.start()
                bound = True
                self.stdout.write(self.style.SUCCESS(f"Model Service gRPC server started and listening on {addr}"))
                break
            except Exception as e:
                last_exc = e
                self.stdout.write(self.style.ERROR(f"Failed to bind to {addr}: {e}"))
                # try next host in BIND_TRIES

        if not bound:
            self.stdout.write(self.style.ERROR("FATAL: gRPC server could not bind to any address."))
            self.stdout.write(self.style.ERROR("Tip: Try running this command manually in an Admin terminal:"))
            self.stdout.write(self.style.ERROR("  GRPC_VERBOSITY=debug python manage.py run_grpc_server"))
            # Exit with non-zero so any launcher that runs this command can detect failure
            raise SystemExit(2)

        try:
            # keep running until stopped
            while True:
                time.sleep(86400)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Stopping gRPC server...'))
            server.stop(0)
