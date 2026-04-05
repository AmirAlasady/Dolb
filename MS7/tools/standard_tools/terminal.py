# MS7/tools/standard_tools/terminal.py

import docker
import time
import logging
import os
import base64
from dotenv import load_dotenv
import uuid 
# Use Python's standard logging for better control and output formatting.
logger = logging.getLogger(__name__)

# Load environment variables in case this module is imported in different contexts.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, '.env'))

try:
    # Connect to the Docker daemon.
    client = docker.from_env()
    # A quick check to ensure the Docker daemon is responsive.
    client.ping()
    logger.info("Successfully connected to the Docker daemon for the terminal tool.")
except docker.errors.DockerException:
    logger.critical("Docker is not running or the client is not configured correctly. The terminal tool will be disabled.")
    client = None

# In-memory session tracking. For a multi-instance MS7 deployment,
# this state must be moved to a shared store like Redis.
SESSION_CONTAINERS = {}

def get_or_create_container(session_id: str, force_recreate: bool = False):
    """
    Finds an existing container or creates a new one. This version proactively
    cleans up any orphaned containers with the same name before creation.
    """
    container_name = f"agent-terminal-session-{session_id}"

    # Proactively clean up old containers if forced or if MS7 has restarted.
    if force_recreate:
        try:
            old_container = client.containers.get(container_name)
            logger.warning(f"Force-recreate requested. Stopping existing container '{container_name}'.")
            # The remove=True flag on the original run command handles the actual deletion.
            old_container.stop(timeout=10)
            if session_id in SESSION_CONTAINERS:
                del SESSION_CONTAINERS[session_id]
        except docker.errors.NotFound:
            pass # Container is already gone, which is the desired state.
        except Exception as e:
            logger.error(f"Error during forced removal of container '{container_name}': {e}")
            if session_id in SESSION_CONTAINERS:
                del SESSION_CONTAINERS[session_id]

    # Try to reuse a running, tracked container
    if session_id in SESSION_CONTAINERS:
        container_id = SESSION_CONTAINERS[session_id]['id']
        try:
            container = client.containers.get(container_id)
            if container.status != 'running':
                container.start()
            SESSION_CONTAINERS[session_id]['last_used'] = time.time()
            return container
        except docker.errors.NotFound:
            del SESSION_CONTAINERS[session_id] # Clean up stale tracker

    # Before creating, ensure no untracked container with the same name exists.
    try:
        existing_container = client.containers.get(container_name)
        logger.warning(f"Found untracked, orphaned container '{container_name}'. Stopping it before creation.")
        existing_container.stop(timeout=10)
    except docker.errors.NotFound:
        pass # Good, no orphan to clean up.
    
    logger.info(f"Creating new container '{container_name}' using image 'superuser-agent-env:latest'...")
    container = client.containers.run(
        "superuser-agent-env:latest", 
        detach=True, 
        tty=True, 
        name=container_name, 
        network_disabled=False, 
        remove=True
    )
    
    SESSION_CONTAINERS[session_id] = { 'id': container.id, 'name': container_name, 'last_used': time.time() }
    logger.info(f"Successfully created container '{container.short_id}' for session '{session_id}'.")
    return container

def run_command(command: str, session_id: str, start_new_session: bool = False, timeout: int = 60) -> str:
    """
    Executes a single, non-interactive shell command inside the sandboxed container.
    This is the simple, robust version. Timeout is handled by the gRPC client.
    """
    logger.info(f"TOOL: run_command | SESSION: {session_id} | CMD: {command}")
    
    if not client:
        return "Error: Docker environment is not available."

    try:
        container = get_or_create_container(session_id, force_recreate=start_new_session)
        
        # Use the simple, non-streaming exec_run. It waits for the command to finish.
        # The gRPC timeout in the MS6 client will handle long-running commands.
        exit_code, output_bytes = container.exec_run(
            cmd=f"sh -c '{command}'",
            workdir="/home/agent/workspace",
            user="agent"
        )
        
        result = output_bytes.decode('utf-8', errors='replace').strip()
        
        # exit_code can be None if the docker daemon has issues, so we check for it.
        if exit_code is None:
             return f"Error: Command '{command}' did not return an exit code. It may have hung or been terminated externally."

        if exit_code != 0:
            return f"Command '{command}' failed with exit code {exit_code}:\n{result}"
            
        return result if result else f"Command '{command}' executed successfully with no output."

    except docker.errors.ImageNotFound:
        return "Error: The 'superuser-agent-env:latest' Docker image was not found. Please build it first."
    except Exception as e:
        logger.error(f"Error in run_command for session {session_id}: {e}", exc_info=True)
        return f"Error: An unexpected system error occurred: {e}"

def transfer_and_run_script(session_id: str, remote_path: str, content: str, ssh_command_prefix: str, post_transfer_command: str = None) -> str:
    """
    The most reliable method for creating and executing scripts on a remote server.
    """
    logger.info(f"TOOL: transfer_and_run_script | SESSION: {session_id} | PATH: {remote_path}")
    if not client: return "Error: The Docker environment is not available."

    try:
        container = get_or_create_container(session_id)
        
        # 1. Create a unique temporary filename inside the container.
        local_temp_filename = f"/home/agent/workspace/temp_script_{uuid.uuid4().hex}.sh"
        
        # 2. Write the content to this local temporary file.
        #    `exec_run` can take input data directly. This avoids all quoting issues.
        container.exec_run(
            cmd=f"tee {local_temp_filename}",
            stdin=True,
            workdir="/home/agent/workspace",
            user="agent"
        ).output # Pass content directly to stdin
        
        # 3. Use `scp` to securely copy the local file to the remote server.
        #    We must extract the user@host from the prefix for scp's syntax.
        user_host = ssh_command_prefix.strip().split(' ')[-1]
        scp_command_prefix = ssh_command_prefix.replace(" ssh ", " scp ", 1)
        scp_command = f"{scp_command_prefix} {local_temp_filename} {user_host}:{remote_path}"
        scp_result = run_command(scp_command, session_id)

        # 4. Clean up the temporary local file inside the container.
        run_command(f"rm {local_temp_filename}", session_id)

        if "failed" in scp_result.lower() or "error" in scp_result.lower():
            return f"Failed to scp file to remote server: {scp_result}"
        
        final_output = f"Successfully transferred script to {remote_path} on the remote server."
        
        # 5. (Optional) Run a command on the remote server after the transfer.
        if post_transfer_command:
            logger.info(f"Executing post-transfer command: {post_transfer_command}")
            remote_exec_command = f"{ssh_command_prefix} \"{post_transfer_command.replace('"', '\\"')}\""
            exec_result = run_command(command=remote_exec_command, session_id=session_id)
            final_output += f"\nPost-transfer command output:\n{exec_result}"
            
        return final_output

    except Exception as e:
        logger.error(f"Error in transfer_and_run_script: {e}", exc_info=True)
        return f"Error: An unexpected system error occurred while transferring the file: {e}"
    




# In MS7/tools/standard_tools/terminal.py
import tarfile
import io

# ... (all existing code: client, get_or_create_container, run_command, etc.)

# --- THIS IS THE NEW, SUPERIOR TOOL THAT REPLACES THE FLAWED scp LOGIC ---
def put_file_in_container(session_id: str, file_path: str, content: str) -> str:
    """
    The most reliable method for writing content to a file inside the sandboxed
    Docker container. It uses the Docker Engine's API directly, bypassing the shell.
    """
    logger.info(f"TOOL: put_file_in_container | SESSION: {session_id} | PATH: {file_path}")
    if not client: return "Error: The Docker environment is not available."

    try:
        container = get_or_create_container(session_id)

        # 1. Create an in-memory TAR archive containing the file.
        #    Docker's `put_archive` requires a TAR stream.
        pw_tarstream = io.BytesIO()
        pw_tar = tarfile.TarFile(fileobj=pw_tarstream, mode='w')
        
        file_data = content.encode('utf-8')
        tarinfo = tarfile.TarInfo(name=os.path.basename(file_path))
        tarinfo.size = len(file_data)
        tarinfo.mtime = time.time()
        
        pw_tar.addfile(tarinfo, io.BytesIO(file_data))
        pw_tar.close()
        pw_tarstream.seek(0)

        # 2. Use the Docker SDK's `put_archive` to copy the TAR into the container.
        #    This is a direct, binary transfer.
        container.put_archive(path=os.path.dirname(file_path), data=pw_tarstream)

        return f"Successfully wrote file to '{file_path}' inside the container."

    except Exception as e:
        logger.error(f"Error in put_file_in_container for session {session_id}: {e}", exc_info=True)
        return f"Error: An unexpected system error occurred while writing the file: {e}"