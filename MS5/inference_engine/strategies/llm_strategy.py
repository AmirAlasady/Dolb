import concurrent.futures
from .base_strategy import BaseCollectionStrategy
# --- FIX 1: Clean and correct imports ---
from inference_internals.clients import ModelServiceClient, ToolServiceClient
# (Future: from inference_internals.clients import MemoryServiceClient)

class LLMCollectionStrategy(BaseCollectionStrategy):
    """
    Strategy for collecting resources for an LLM job.
    Gathers model configuration and, if enabled, tool definitions, memory, etc.
    """
    def collect_resources(self) -> dict:
        # --- FIX 2: Use a single dictionary to store all collected resources ---
        collected_resources = {
            "model_config": {},
            "tools": [],
            "memory_context": None,
            "rag_documents": None,
        }

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_resource = {}
            
            # --- Submit Model Config Task (unchanged) ---
            model_id = self.node_config.get("configuration", {}).get("model_config", {}).get("model_id")
            if not model_id:
                raise ValueError("Node configuration is missing a model_id.")
            
            model_client = ModelServiceClient()
            future_model = executor.submit(model_client.get_model_configuration, model_id, self.user_id)
            future_to_resource[future_model] = "model_config"

            # --- Submit Tool Definitions Task (unchanged logic, just integrated) ---
            tool_config = self.node_config.get("configuration", {}).get("tool_config", {})
            if "tool_ids" in tool_config and tool_config["tool_ids"]:
                tool_client = ToolServiceClient()
                future_tools = executor.submit(
                    tool_client.get_tool_definitions,
                    tool_config["tool_ids"],
                    self.user_id
                )
                future_to_resource[future_tools] = "tools"

            # --- Submit Memory Task (if enabled) ---
            # ... (your future memory logic would go here)

            # --- Process results as they complete ---
            for future in concurrent.futures.as_completed(future_to_resource):
                resource_name = future_to_resource[future]
                try:
                    result = future.result()
                    # --- FIX 3: Store the result in the correct dictionary key ---
                    collected_resources[resource_name] = result

                except Exception as exc:
                    print(f'Resource collection for "{resource_name}" failed: {exc}')
                    raise # Re-raise the exception to fail the entire request

        # --- FIX 4: Return the complete dictionary ---
        return collected_resources