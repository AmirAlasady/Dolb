import httpx
import importlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from .models import Tool

class ToolExecutor:
    """
    Handles the dynamic execution of tools based on their definition.
    This class is the single point of entry for running any tool.
    """
    def _execute_internal_function(self, pointer: str, arguments: dict):
        try:
            module_name, func_name = pointer.rsplit('.', 1)
            module = importlib.import_module(module_name)
            func_to_execute = getattr(module, func_name)
            return func_to_execute(**arguments)
        except (ImportError, AttributeError) as e:
            raise RuntimeError(f"Could not find or import internal function: {pointer}. Error: {e}")

    def _execute_webhook(self, config: dict, arguments: dict):
        """
        Executes a webhook tool, dynamically choosing the HTTP method (GET or POST)
        based on the tool's definition.
        """
        url = config.get("url")
        # Default to POST if not specified, but read the method from the config.
        method = config.get("method", "POST").upper()
        
        if not url:
            raise ValueError("Webhook execution config is missing 'url'.")
        
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        # ... (authentication logic for webhooks can be added here if needed)

        print(f"Executing webhook with method '{method}' to URL '{url}'")
        
        with httpx.Client(timeout=10.0) as client:
            try:
                response = None
                if method == 'GET':
                    # For GET requests, arguments are sent as query parameters.
                    response = client.get(url, params=arguments, headers=headers)
                elif method == 'POST':
                    # For POST requests, arguments are sent in the JSON body.
                    response = client.post(url, json=arguments, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method for webhook: '{method}'")

                response.raise_for_status()
                
                # Handle cases where the response might be empty (e.g., a 204 No Content)
                if response.status_code == 204:
                    return {"status": "success", "message": "Operation completed successfully with no content returned."}
                    
                return response.json()
            
            except httpx.RequestError as e:
                raise RuntimeError(f"Error calling webhook {url}: {e}")
            except httpx.HTTPStatusError as e:
                # This will now correctly report the 405 error if it still occurs,
                # but also includes the response body for better debugging.
                raise RuntimeError(f"Client error '{e.response.status_code} {e.response.reason_phrase}' for url '{e.request.url}'. Response body: {e.response.text}")
    # --- END OF FIX ---

    def execute_single_tool(self, tool_call: dict) -> dict:
        """Executes one tool call and returns the result."""
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})

        try:
            tool = Tool.objects.get(name=tool_name) # Assuming user is already authorized
            
            # Handle potentially nested definition
            actual_def = tool.definition.get("definition", tool.definition) if isinstance(tool.definition.get("definition"), dict) else tool.definition
            
            execution_config = actual_def.get("execution", {})
            exec_type = execution_config.get("type")

            if exec_type == "internal_function":
                result_content = self._execute_internal_function(execution_config.get("pointer"), arguments)
            elif exec_type == "webhook":
                result_content = self._execute_webhook(execution_config, arguments)
            else:
                raise ValueError(f"Unknown execution type for tool '{tool_name}': {exec_type}")

            return {
                "tool_call_id": tool_call.get("id"),
                "name": tool_name,
                "status": "success",
                "output": json.dumps(result_content) # Ensure output is a JSON string
            }
        except Exception as e:
            return {
                "tool_call_id": tool_call.get("id"),
                "name": tool_name,
                "status": "error",
                "output": str(e)
            }

    def execute_parallel_tools(self, tool_calls: list[dict]) -> list[dict]:
        """
        Executes a list of tool calls in parallel using a thread pool.
        This is the primary method used by the gRPC servicer.
        """
        results = []
        with ThreadPoolExecutor() as executor:
            future_to_call = {executor.submit(self.execute_single_tool, call): call for call in tool_calls}
            for future in as_completed(future_to_call):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    # This catches errors within the future execution itself
                    call = future_to_call[future]
                    results.append({
                        "tool_call_id": call.get("id"),
                        "name": call.get("name"),
                        "status": "error",
                        "output": f"An unexpected execution error occurred: {e}"
                    })
        return results

# A single instance to be used by the gRPC servicer
tool_executor = ToolExecutor()