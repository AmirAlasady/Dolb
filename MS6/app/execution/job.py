# MS6/app/execution/job.py
import uuid
from app.logging_config import logger

class Job:
    """
    A data class providing a clean, validated, and DEFENSIVE interface
    to the raw job payload from MS5.
    """
    def __init__(self, payload: dict):
        if not isinstance(payload, dict):
            raise TypeError("Job payload must be a dictionary.")
        self.id = payload.get("job_id", payload.get("run_id", str(uuid.uuid4())))
        # Capture MS15 specific fields into metadata if present at top level
        self.metadata = payload.get("metadata", {})
        for key in ["run_id", "rule_id", "attempt_id"]:
            if key in payload and key not in self.metadata:
                self.metadata[key] = payload[key]
        self.user_id = payload.get("user_id")
        self.jwt_token = payload.get("jwt_token") 
        self.project_id = payload.get("project_id")
        # The entire original request body from Postman is nested under the 'query' key.
        self.query = payload.get("query", {})
        
        self.prompt_text = self.query.get("prompt", "")
        self.inputs = self.query.get("inputs", [])
        self.default_params = payload.get("default_parameters", {})
        self.param_overrides = self.query.get("parameter_overrides", {})
        
        # --- THE DEFINITIVE FIX IS HERE ---
        # We must get the output_config from the nested query object.
        self.output_config = self.query.get("output_config", {})
        
        self.is_streaming = self.output_config.get("mode") == "streaming"
        self.persist_inputs_in_memory = self.output_config.get("persist_inputs_in_memory", False)

        # Log the decision made during initialization.
        logger.info(f"[{self.id}] Job class initialized. persist_inputs_in_memory flag is set to: {self.persist_inputs_in_memory}")
        # --- END OF FIX ---

        self.resources = payload.get("resources") or {}
        
        self.model_config = self.resources.get("model_config", {})
        self.tool_definitions = self.resources.get("tools")
        rag_context = self.resources.get("rag_context") or {}
        self.rag_docs = rag_context.get("chunks", [])
        self.memory_context = self.resources.get("memory_context") or {}
    
    @property
    def feedback_ids(self):
        return {
            "memory_bucket_id": self.memory_context.get("bucket_id"),
            "rag_collection_id": (self.resources.get("rag_context") or {}).get("collection_id")
        }