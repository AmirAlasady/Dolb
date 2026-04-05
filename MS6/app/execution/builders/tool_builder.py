# MS6/app/execution/builders/tool_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from app.internals.clients import ToolServiceClient
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model
import uuid
from typing import Optional # <-- Import Optional for type hinting

class MicroserviceToolExecutor:
    """
    A callable class that encapsulates the state and logic needed to execute
    a single tool via a gRPC microservice.
    """
    def __init__(self, client: ToolServiceClient, job_id: str, tool_name: str, required_params: list[str]):
        self.client = client
        self.job_id = job_id
        self.tool_name = tool_name
        self.required_params = required_params

    async def __call__(self, **kwargs):
        """
        This is the async method that LangChain's AgentExecutor will call.
        It accepts the arguments provided by the LLM as keyword arguments.
        """
        arguments = kwargs
        
        # This existing logic for session_id injection remains correct and functional.
        if 'session_id' in self.required_params and 'session_id' not in arguments:
            logger.info(f"[{self.job_id}] Injecting job_id as session_id for tool '{self.tool_name}'.")
            arguments['session_id'] = self.job_id

        tool_call_id = f"{self.job_id}-{self.tool_name}-{uuid.uuid4()}"
        tool_call_payload = [{"id": tool_call_id, "name": self.tool_name, "arguments": arguments}]
        
        logger.info(f"[{self.job_id}] Agent requested to execute tool '{self.tool_name}' with args: {arguments}")
        results = await self.client.execute_tools(tool_call_payload)
        
        output = f"Error: No result from tool '{self.tool_name}'."
        if results and results[0]['status'] == 'success':
            output = results[0]["output"]
        elif results:
            output = f"Error from tool '{self.tool_name}': {results[0]['output']}"

        logger.info(f"[{self.job_id}] Tool '{self.tool_name}' returned: {output[:100]}...")
        return output

class ToolBuilder(BaseBuilder):
    """
    Creates LangChain-compatible tool objects from tool definitions.
    This definitive version uses a callable class for execution and correctly
    handles both required and optional tool parameters.
    """
    def __init__(self):
        self.tool_service_client = ToolServiceClient()

    async def build(self, context: BuildContext) -> BuildContext:
        if not context.job.tool_definitions:
            return context
        
        logger.info(f"[{context.job.id}] Building {len(context.job.tool_definitions)} tools.")
        
        for definition in context.job.tool_definitions:
            tool_name = definition["name"]
            # Robust parsing of description and parameters
            # Handle cases where the definition might be nested under a 'definition' key
            # or missing the description field entirely.
            actual_def = definition.get("definition", definition) if isinstance(definition.get("definition"), dict) else definition
            
            tool_description = actual_def.get("description") or definition.get("description") or f"Execution of tool {tool_name}"
            tool_params_schema = actual_def.get("parameters") or definition.get("parameters") or {}
            
            tool_params = tool_params_schema.get("properties", {})
            required_params = tool_params_schema.get("required", [])
            
            # --- THE DEFINITIVE FIX IS HERE (INTEGRATED INTO YOUR EXISTING CODE) ---
            fields_for_model = {}
            for param_name, schema in tool_params.items():
                param_description = schema.get("description", "")
                
                # If the parameter name is in the 'required' list from the tool definition...
                if param_name in required_params:
                    # ...make it a required field in the Pydantic model (using ...).
                    fields_for_model[param_name] = (str, Field(..., description=param_description))
                else:
                    # ...otherwise, make it optional by giving it a default value of None.
                    fields_for_model[param_name] = (Optional[str], Field(default=None, description=param_description))
            # --- END OF FIX ---
            
            DynamicArgsSchema = create_model(f"{tool_name}ArgsSchema", **fields_for_model)

            # This part of your code is already the optimal design.
            tool_executor = MicroserviceToolExecutor(
                client=self.tool_service_client,
                job_id=context.job.id,
                tool_name=tool_name,
                required_params=required_params
            )

            dynamic_tool = StructuredTool.from_function(
                name=tool_name,
                description=tool_description,
                args_schema=DynamicArgsSchema,
                coroutine=tool_executor,
                verbose=True
            )
            
            context.tools.append(dynamic_tool)

        logger.info(f"[{context.job.id}] Tools built successfully.")
        return context