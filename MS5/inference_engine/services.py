# MS5/inference_engine/services.py

import uuid
import json
from datetime import datetime
import concurrent.futures
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
import logging

from .ticket_manager import generate_ticket
from inference_internals.clients import (
    NodeServiceClient,
    ModelServiceClient,
    ToolServiceClient,
    MemoryServiceClient,
    DataServiceClient,
    RAGServiceClient 
)
from messaging.event_publisher import inference_job_publisher

logger = logging.getLogger(__name__)

class InferenceOrchestrationService:
    def __init__(self):
        self.node_client = NodeServiceClient()
        self.model_client = ModelServiceClient()
        self.tool_client = ToolServiceClient()
        self.memory_client = MemoryServiceClient()
        self.data_client = DataServiceClient()
        self.rag_client = RAGServiceClient()

    def process_inference_request(self, node_id: str, user_id: str, query_data: dict,  jwt_token: str):
        job_id = str(uuid.uuid4())
        logger.info(f"--- [JOB {job_id}] ORCHESTRATION STARTED ---")
        logger.info(f"    Node ID: {node_id} | User ID: {user_id}")

        # STAGE 1: Fetch Node details first, as it dictates the rest of the flow.
        logger.info(f"[{job_id}] Stage 1: Fetching primary Node details...")
        node_details = self.node_client.get_node_details(node_id, user_id)
        
        # Perform initial, critical validation on the Node itself.
        if node_details.get("status") in ["inactive", "draft"]:
            raise PermissionDenied(f"Node is in status '{node_details.get('status')}' and cannot be used for inference.")
        
        node_config = node_details.get("configuration", {})
        model_id = node_config.get("model_config", {}).get("model_id")
        if not model_id:
            raise ValidationError("Node is not configured with a valid model.")

        # STAGE 2: Fetch all dependent resources needed for validation in parallel.
        logger.info(f"[{job_id}] Stage 2: Fetching dependent resources for validation in parallel...")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_model = executor.submit(self.model_client.get_model_configuration, model_id, user_id)
            
            future_files = None
            file_ids_to_validate = [inp['id'] for inp in query_data.get("inputs", []) if inp.get('type') == 'file_id']
            if file_ids_to_validate:
                future_files = executor.submit(self.data_client.get_file_metadata, file_ids_to_validate, user_id)

            model_details = future_model.result()
            files_metadata = future_files.result() if future_files else []
        
        logger.info(f"[{job_id}] Stage 2: Dependent resources fetched.")

        # STAGE 3: Perform the validation gauntlet with the data we now have.
        self._validate_request_inputs(node_details, model_details, files_metadata) # This method name is updated
        logger.info(f"[{job_id}] Stage 3: Pre-flight input validation passed.")

        # STAGE 4: Dynamically collect any remaining optional resources (like memory and tools).
        # This is where your original _collect_resources_dynamically logic is preserved.
        logger.info(f"[{job_id}] Stage 4: Collecting optional resources (memory, tools, rag)...")
        collected_resources = self._collect_optional_resources(
            job_id, user_id, node_config, model_details, query_data
        )
        logger.info(f"[{job_id}] Stage 4: Optional resources collection finished.")

        # STAGE 5: Assemble and dispatch the final job payload.
        # This is where your original _assemble_job_payload logic is preserved.
        logger.info(f"[{job_id}] Stage 5: Assembling and dispatching job payload...")
        job_payload = self._assemble_job_payload(
            job_id, user_id, node_details, query_data, collected_resources, jwt_token
        )
        
        ws_ticket = generate_ticket(job_id=job_payload["job_id"], user_id=user_id)
        inference_job_publisher.publish_job(job_payload)
        logger.info(f"[{job_id}] Stage 6: Job published to queue.")
        logger.info(f"--- [JOB {job_id}] ORCHESTRATION FINISHED ---")

        return {"job_id": job_payload["job_id"], "status": "Job submitted successfully.", "websocket_ticket": ws_ticket}

    def _validate_request_inputs(self, node_details: dict, model_details: dict, files_metadata: list[dict]):
        """
        Performs the file compatibility check against model capabilities.
        """
        if not files_metadata:
            return

        model_capabilities = model_details.get("capabilities", [])
        logger.info(f"[{node_details.get('id')}] Validating file types against model capabilities: {model_capabilities}")

        for file_meta in files_metadata:
            mimetype = file_meta.get('mimetype', '')
            file_id = file_meta.get('file_id') # Changed from 'filename' to be consistent

            if mimetype.startswith('image/'):
                if 'image' not in model_capabilities:
                    raise ValidationError(f"File {file_id} is an image, but the selected model does not support image inputs.")
            elif mimetype in [
                'application/pdf', 
                'text/plain', 
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            ]:
                if 'text' not in model_capabilities:
                    raise ValidationError(f"File {file_id} is a text document, but the selected model does not support text inputs.")
            else:
                logger.warning(f"Validation for mimetype '{mimetype}' is not implemented. Allowing by default.")

    def _collect_optional_resources(self, job_id: str, user_id: str, node_config: dict, model_details: dict, query_data: dict) -> dict:
        """
        This is your original method, with the new RAG logic ADDED to it.
        """
        collected_resources = {"model_config": model_details}
        overrides = query_data.get("resource_overrides", {})

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_resource = {}
            
            # This is your original, correct logic for tools
            if tool_config := node_config.get("tool_config"):
                if tool_ids := tool_config.get("tool_ids"):
                    logger.info(f"[{job_id}] Submitting task: GetToolDefinitions for {len(tool_ids)} tool(s).")
                    future = executor.submit(self.tool_client.get_tool_definitions, tool_ids, user_id)
                    future_to_resource[future] = "tools"

            # NEW GATEKEEPER LOGIC: MS4's is_enabled is the ABSOLUTE authority.
            # We ignore MS5 overrides to ensure the node follows its blueprint.
            if memory_config := node_config.get("memory_config"):
                should_use_memory = memory_config.get("is_enabled", False)
                
                if should_use_memory:
                    bucket_id = memory_config.get("bucket_id")
                    if not bucket_id:
                        logger.warning(f"[{job_id}] Memory is ENABLED in MS4 but no 'bucket_id' is configured. Skipping.")
                    else:
                        logger.info(f"[{job_id}] Memory is ENABLED (Authority: MS4). Fetching history for: {bucket_id}")
                        future = executor.submit(self.memory_client.get_history, bucket_id, user_id)
                        future_to_resource[future] = "memory_context"
                else:
                    logger.info(f"[{job_id}] Memory is DISABLED (Authority: MS4). Ignoring any overrides.")

            if rag_config := node_config.get("rag_config"):
                should_use_rag = rag_config.get("is_enabled", False)
                
                if should_use_rag:
                    collection_id = rag_config.get("collection_id")
                    if collection_id:
                        logger.info(f"[{job_id}] RAG is ENABLED (Authority: MS4). Fetching chunks for: {collection_id}")
                        future = executor.submit(
                            self.rag_client.RetrieveRelevantChunks,
                            collection_id=collection_id,
                            user_id=user_id,
                            query=query_data.get("prompt", "")
                        )
                        future_to_resource[future] = "rag_context"
                    else:
                        logger.warning(f"[{job_id}] RAG is ENABLED in MS4 but no 'collection_id' configured. Skipping.")
                else:
                    logger.info(f"[{job_id}] RAG is DISABLED (Authority: MS4). Ignoring any overrides.")

            for future in concurrent.futures.as_completed(future_to_resource):
                resource_name = future_to_resource[future]
                try:
                    collected_resources[resource_name] = future.result()
                    logger.info(f"[{job_id}] --> Successfully collected optional resource: '{resource_name}'")
                except Exception as exc:
                    logger.error(f"[{job_id}] --> FAILED to collect optional resource: '{resource_name}'. Reason: {exc}", exc_info=True)
                    raise exc
        
        return collected_resources

    def _assemble_job_payload(self, job_id: str, user_id: str, node_details: dict, query_data: dict, resources: dict, jwt_token: str) -> dict:
        """
        Assembles the final job payload. 
        Explicitly sets persistence flags based on calculated resources.
        """
        node_config = node_details.get("configuration", {})
        
        # Ensure output_config exists and reflect the actual collection state
        if "output_config" not in query_data:
            query_data["output_config"] = {}
        
        # ABSOLUTE AUTHORITY: If the resource was collected (meaning MS4 is enabled),
        # then we enable persistence. If it wasn't, we disable it. 
        # This prevents MS5 request overrides from turning OFF a feature that is ON in MS4.
        has_memory = "memory_context" in resources
        query_data["output_config"]["persist_inputs_in_memory"] = has_memory

        final_resources = {
            "model_config": resources.get("model_config"),
            "tools": resources.get("tools"),
            "rag_context": resources.get("rag_context"),
            "memory_context": resources.get("memory_context"),
        }
        
        return {
            "job_id": job_id,
            "user_id": user_id,
            "project_id": node_details.get("project_id"),
            "jwt_token": jwt_token,
            "timestamp": datetime.utcnow().isoformat(),
            "query": query_data,
            "default_parameters": node_config.get("model_config", {}).get("parameters", {}),
            "resources": final_resources
        }


    # for graph execution from ms15
    def process_graph_request(self, payload: dict):
        """
        Handles requests coming from MS15 (Graph Engine).
        Consolidated to use _assemble_job_payload for policy consistency.
        """
        run_id = payload.get("run_id")
        rule_id = payload.get("rule_id")
        node_id = payload.get("node_id")
        ms4_node_id = payload.get("ms4_node_id")
        user_id = "system"
        
        if "metadata" in payload and "user_id" in payload["metadata"]:
             user_id = payload["metadata"]["user_id"]
        
        lookup_id = ms4_node_id or node_id
        temp_job_id = payload.get("attempt_id")

        logger.info(f"[{run_id}::{rule_id}] Orchestrating graph node (attempt {temp_job_id})...")

        # 1. Fetch Node & Model Configurations
        node_details = self.node_client.get_node_details(lookup_id, user_id)
        node_config = node_details.get("configuration", {})
        
        model_id = node_config.get("model_config", {}).get("model_id")
        model_details = self.model_client.get_model_configuration(model_id, user_id)

        # 2. Collect Optional Resources (Tools, RAG, History)
        query_data = {
            "prompt": payload.get("prompt_text"),
            "resource_overrides": {},
            "output_config": {
                "persist_inputs_in_memory": True # Graphs follow MS4 by default
            },
            "inputs": [{"id": file_id, "type": "file_id"} for file_id in payload.get("file_ids", [])]
        }
        
        # Validate files just like the normal API
        file_ids_to_validate = [inp['id'] for inp in query_data.get("inputs", []) if inp.get('type') == 'file_id']
        if file_ids_to_validate:
            logger.info(f"[{run_id}::{rule_id}] Validating {len(file_ids_to_validate)} attached file(s)...")
            files_metadata = self.data_client.get_file_metadata(file_ids_to_validate, user_id)
            self._validate_request_inputs(node_details, model_details, files_metadata)
        
        collected_resources = self._collect_optional_resources(
            temp_job_id, user_id, node_config, model_details, query_data
        )

        # 3. Assemble Payload using the unified method to enforce policy
        job_payload = self._assemble_job_payload(
            temp_job_id, user_id, node_details, query_data, collected_resources, None
        )

        # 4. Final Metadata Adjustment (Preserve MS15 IDs)
        final_metadata = payload.get("metadata", {})
        final_metadata.update({
            "run_id": run_id,
            "rule_id": rule_id,
            "node_id": node_id,
            "attempt_id": temp_job_id
        })
        job_payload["metadata"] = final_metadata

        # 5. Dispatch to RabbitMQ
        inference_job_publisher.publish_job(job_payload)
        logger.info(f"[{run_id}::{rule_id}] Dispatched via Authoritative Policy.")
        logger.info(f"[{run_id}::{rule_id}] Dispatched to MS6.")