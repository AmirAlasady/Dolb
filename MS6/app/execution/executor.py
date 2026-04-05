# MS6/app/execution/executor.py

import re
import uuid

from pyparsing import Any
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessageChunk, BaseMessage, AIMessage, ToolMessage
from PIL import Image
import io
import json
import requests
import base64
from langchain.agents import create_tool_calling_agent
from app.logging_config import logger
from app.execution.build_context import BuildContext
from app.messaging.publisher import ResultPublisher
from app.internals.clients import DataServiceClient
from langchain.agents import AgentExecutor
from langchain.agents.format_scratchpad.tools import format_to_tool_messages
from langchain.agents.output_parsers.tools import ToolsAgentOutputParser
# This one might already be there, but ensure it is
from langchain.agents import create_tool_calling_agent
from langchain.agents.output_parsers.tools import ToolsAgentOutputParser
# This is the new, crucial import
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.agents import AgentExecutor, create_openai_tools_agent
import asyncio
# This is the NEW, CORRECT parser we need to import
# And we need the tool conversion utility
# --- END OF IMPORTS ---
import json
from typing import Any
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
import re
import json
import uuid
import asyncio
from typing import List, Any, Tuple
from langchain_core.messages import AIMessage
from app.logging_config import logger





class LRSAgentExecutor:


    
    def __init__(self, llm, prompt, tools, jobid, publisher):
        self.llm = llm
        self.tools = {tool.name: tool for tool in tools }
        self.jobid = jobid
        self.publisher = publisher
        self.prompt = prompt
        self.max_iterations = 50 # Prevent infinite loops

    def _format_scratchpad(self, intermediate_steps: List[Tuple[dict, Any]]) -> List[AIMessage]:
        """
        Turn intermediate_steps (list of (action, observation)) into a list of AIMessage
        objects containing text the model will see. We intentionally avoid ToolMessage
        so we don't rely on ChatLRS to render ToolMessage.
        Each action is rendered as the exact token + fenced JSON the model expects,
        followed by an "Assistant observed:" line with the tool output.
        """
        out: List[AIMessage] = []
        for action, observation in intermediate_steps:
            # Normalize action -> {"tool": name, "tool_input": {...}}
            call_obj = {"tool": action.get("name") or action.get("tool") or action.get("action"),
                        "tool_input": action.get("args", action.get("tool_input", {}))}
            call_json = json.dumps([call_obj], indent=2, ensure_ascii=False)
            tool_call_text = f"<|tool_call|>\n```json\n{call_json}\n```"
            out.append(AIMessage(content=tool_call_text))

            # Put the tool observation as plain assistant text so ChatLRS includes it
            # Trim very long observations to avoid token bloat
            obs_text = str(observation or "")
            max_obs = 2000
            if len(obs_text) > max_obs:
                obs_text = obs_text[:max_obs] + "...(truncated)"
            out.append(AIMessage(content=f"Tool Output ({call_obj['tool']}):\n{obs_text}"))

        return out
        
    async def _parse_tool_calls(self, response: str) -> list[dict] | None:
        """
        A robust parser that extracts a JSON block from a string,
        even if it's wrapped in markdown.
        """
        if not response or "<|tool_call|>" not in response:
            return None
        
        # Use a regular expression to find the content between ```json and ```
        match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        
        if not match:
            # Fallback for if the model forgets the markdown
            try:
                potential_json = response.split("<tool_call>").strip()
                parsed_json = json.loads(potential_json)
                if isinstance(parsed_json, list):
                    return parsed_json
            except:
                return None
            return None

        json_string = match.group(1).strip()
        try:
            parsed_json = json.loads(json_string)
            if isinstance(parsed_json, list):
                return parsed_json
        except json.JSONDecodeError as e:
            logger.error(f"[{self.jobid}] Failed to parse extracted JSON: {e}")
        
        return None

    async def ainvoke(self, inputs: dict) -> dict:
        """
        Custom agent loop. Inputs expected to be dict compatible with your prompt template.
        Uses self.llm.ainvoke(prompt_value) to call ChatLRS (unchanged).
        """
        intermediate_steps: List[Tuple[dict, Any]] = []
        final_inputs = inputs.copy()

        # repeat-detection: map action signature -> count
        repeat_counts = {}
        MAX_REPEAT = 3

        for iteration in range(self.max_iterations):
            logger.info(f"[{self.jobid}] --- Custom Agent Loop: Iteration {iteration + 1} ---")

            # Build the scratchpad that ChatLRS will render (AIMessage list)
            scratchpad_ai_messages = self._format_scratchpad(intermediate_steps)
            # Put into the input the prompt expects under 'agent_scratchpad'
            # Your prompt_template.ainvoke likely expects a list of messages there.
            final_inputs["agent_scratchpad"] = scratchpad_ai_messages

            # Call the llm (ChatLRS.ainvoke) with the prompt template output
            prompt_value = await self.prompt.ainvoke(final_inputs)  # prompt template -> messages or string
            response_message = await self.llm.ainvoke(prompt_value)
            raw_output = getattr(response_message, "content", "") or ""
            logger.info(f"[{self.jobid}] Raw LLM Output:\n{raw_output}")

            # Parse tool calls
            tool_calls = await self._parse_tool_calls(raw_output)

            if not tool_calls:
                logger.info(f"[{self.jobid}] Agent finished with final answer.")
                return {"output": raw_output}

            logger.info(f"[{self.jobid}] Agent decided to call {len(tool_calls)} tool(s).")

            # Build normalized action dicts
            actions = []
            for call in tool_calls:
                name = call.get("tool") or call.get("name")
                args = call.get("tool_input", {})
                actions.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "name": name,
                    "args": args
                })

            # Repeat-detection: if same action called repeatedly, stop after MAX_REPEAT
            sig = tuple((a["name"], json.dumps(a.get("args", {}), sort_keys=True)) for a in actions)
            repeat_counts[sig] = repeat_counts.get(sig, 0) + 1
            if repeat_counts[sig] > MAX_REPEAT:
                logger.warning(f"[{self.jobid}] Detected repeated identical action {actions[0]['name']} x{repeat_counts[sig]}. Aborting to avoid loop.")
                return {"output": f"Aborted due to repeated tool calls to {actions[0]['name']}"}

            # Execute tools concurrently
            tasks = []
            for action in actions:
                tool_name = action["name"]
                tool_input = action["args"]
                # logger.info(f"[{self.jobid}] Agent requested to execute tool '{tool_name}' with args: {tool_input}")
                if tool_name not in self.tools:
                    async def _not_found(tool=tool_name):
                        return f"Error: Tool '{tool}' not found."
                    tasks.append(_not_found())
                else:
                    try:
                        coro = self.tools[tool_name].coroutine(**tool_input)
                        tasks.append(coro)
                    except Exception as e:
                        async def _err(e=e, tn=tool_name):
                            return f"Error scheduling tool '{tn}': {e}"
                        tasks.append(_err())

            # gather results (will raise if tasks crash unless you want exceptions)
            observations = await asyncio.gather(*tasks, return_exceptions=False)

            # append to scratchpad
            for action, obs in zip(actions, observations):
                intermediate_steps.append((action, obs))

            # continue loop and LLM will see new scratchpad in next iteration

        # hit max iterations
        logger.warning(f"[{self.jobid}] Agent reached max iterations ({self.max_iterations}). Stopping.")
        return {"output": "Agent stopped after reaching max iterations."}

class Executor:
    def __init__(self, context: BuildContext, publisher: ResultPublisher):
        self.context = context
        self.job = context.job
        self.publisher = publisher

    def _get_final_content(self, result: any) -> any:
        """
        Safely extracts the final content, which can be a string, a dict (from an agent),
        or a complex object like a PIL Image.
        """
        if isinstance(result, dict) and 'output' in result:
            return result.get('output')
        elif isinstance(result, BaseMessage):
            return result.content
        return result

    async def _handle_image_generation_output(self, content_from_llm) -> dict:
        """
        A universal handler that processes potential image outputs from any provider
        and uploads the result to the Data Service.
        """
        image_bytes = None
        
        # Case 1: Google Gemini returns a PIL Image object
        if isinstance(content_from_llm, Image.Image):
            logger.info(f"[{self.job.id}] Processing PIL.Image object.")
            byte_arr = io.BytesIO()
            content_from_llm.save(byte_arr, format='PNG')
            image_bytes = byte_arr.getvalue()
            
        # Case 2: OpenAI DALL-E returns a JSON string containing a URL
        elif isinstance(content_from_llm, str):
            try:
                data = json.loads(content_from_llm)
                if isinstance(data, list) and data[0].get("type") == "image_url":
                    image_url = data[0]["image_url"]["url"]
                    logger.info(f"[{self.job.id}] Processing URL from DALL-E: {image_url}")
                    response = requests.get(image_url, timeout=30)
                    response.raise_for_status()
                    image_bytes = response.content
            except (json.JSONDecodeError, KeyError, IndexError, requests.RequestException):
                    # This wasn't a DALL-E response, it's just a regular string.
                    # We'll let the outer logic handle it.
                    pass

        if image_bytes:
            if not self.job.project_id:
                raise ValueError("Cannot upload generated image: project_id not found in job payload.")
            if not self.job.jwt_token:
                raise ValueError("Cannot upload generated image: jwt_token not found for delegated authentication.")

            new_file_metadata = await DataServiceClient.upload_generated_image(
                image_bytes=image_bytes,
                user_id=self.job.user_id,
                project_id=self.job.project_id,
                jwt_token=self.job.jwt_token
            )
            
            return {
                "type": "generated_image",
                "file_id": new_file_metadata.get("id"),
                "filename": new_file_metadata.get("filename")
            }
        
        # If no image was processed, return the original content
        return content_from_llm

    async def run(self):
        logger.info(f"[{self.job.id}] Starting final chain execution.")
        
        model_capabilities = self.job.model_config.get("capabilities", [])
        can_generate_images = "image_generation" in model_capabilities
        logger.info(f"[{self.job.id}] Model capabilities: {model_capabilities}. Image generation expected: {can_generate_images}")
        
        if self.context.tools:
            # Check if the model supports the modern, efficient .bind_tools() method.
            # Official, modern models (OpenAI, Google, Anthropic) have this.
            # Our custom BaseChatModel does not.
            if getattr(self.context.llm, '_llm_type', None) != 'chat_lrs':
                logger.info(f"[{self.job.id}] Tools detected. Using modern 'create_tool_calling_agent' method.")
                
                # --- OLD LOGIC PATH (UNCHANGED) ---
                # This is your original, working code for models that support it.
                # It is preserved exactly as it was.
                agent = create_tool_calling_agent(self.context.llm, self.context.tools, self.context.prompt_template)
                runnable = AgentExecutor(agent=agent, tools=self.context.tools, verbose=True)
                # --- END OF OLD LOGIC PATH ---

            else:
                logger.info(f"[{self.job.id}] Tools detected for LRS model. Using CUSTOM Agent Executor.")
                # We instantiate OUR OWN executor, not LangChain's
                runnable = LRSAgentExecutor(
                    llm=self.context.llm,
                    tools=self.context.tools,
                    prompt=self.context.prompt_template,
                    jobid=self.job.id,
                    publisher=self.publisher
                )
        else:
            logger.info(f"[{self.job.id}] Assembling a simple LLM chain (no tools).")
            runnable = self.context.prompt_template | self.context.llm
        
        if self.context.memory:
            self.context.final_input["chat_history"] = self.context.memory
            logger.info(f"[{self.job.id}] Added {len(self.context.memory)} messages from history to the input.")
        
        # 3. Execute the chain and handle the output.
        if self.job.is_streaming:
            final_result = await self._stream_and_publish(runnable, self.context.final_input)
        else:
            result = await runnable.ainvoke(self.context.final_input)
            final_result = self._get_final_content(result)
            logger.info(f"[{self.job.id}] FINAL BLOCKING RESPONSE:\n---\n{final_result}\n---")
            await self.publisher.publish_final_result(self.job.id, final_result, metadata=self.job.metadata)
        
        # 4. Trigger the memory feedback loop after the job is fully complete.
        await self.publisher.publish_memory_update(self.job, final_result, self.context.final_input) # new update



    async def _stream_and_publish(self, chain, input_data: dict) -> str:
        """
        Handles streaming the output of a LangChain runnable.
        This version is backward-compatible: it uses a conditional check to handle
        the modern streaming format for LRS models, while preserving the old
        logic for all other existing models.
        """
        final_result = ""
        logger.info(f"[{self.job.id}] Executing in streaming mode.")
        try:
            # --- CONDITIONAL LOGIC FOR BACKWARD COMPATIBILITY ---
            
            # Check if we are using our new ChatLRS model by looking for the
            # unique _llm_type property we defined on that custom class.
            is_lrs_model = hasattr(self.context.llm, '_llm_type') and self.context.llm._llm_type == 'chat_lrs'

            async for chunk in chain.astream(input_data):
                output_chunk = ""

                # --------------------------------------------------------------------
                # NEW LOGIC PATH: For our LRS model, handle the modern AIMessageChunk.
                # --------------------------------------------------------------------
                if is_lrs_model:
                    # For simple LRS chains, the chunk is the AIMessageChunk itself.
                    if isinstance(chunk, AIMessageChunk):
                        output_chunk = chunk.content
                    # For LRS agents, the chunk is a dict containing a list of messages.
                    elif isinstance(chunk, dict) and 'messages' in chunk:
                        for message in chunk['messages']:
                            if isinstance(message, AIMessageChunk):
                                output_chunk = message.content
                
                # --------------------------------------------------------------------
                # OLD LOGIC PATH: For all other models (Google, OpenAI, etc.),
                # the existing logic remains completely untouched.
                # --------------------------------------------------------------------
                else:
                    if isinstance(chunk, dict):
                        messages = chunk.get('messages', [])
                        if messages and isinstance(messages[-1], AIMessageChunk):
                            output_chunk = messages[-1].content
                    elif isinstance(chunk, AIMessageChunk):
                        output_chunk = chunk.content
                
                # This part is common to both paths: publish any valid text chunk.
                if isinstance(output_chunk, str) and output_chunk:
                    await self.publisher.publish_stream_chunk(self.job.id, output_chunk)
                    final_result += output_chunk
            # --- END OF CONDITIONAL LOGIC ---

        except Exception as e:
            logger.error(f"[{self.job.id}] An error occurred during streaming: {e}", exc_info=True)
            await self.publisher.publish_error_result(self.job.id, f"An error occurred during streaming: {e}")
            return ""
        
        # This part is also common and runs after the loop finishes successfully.
        logger.info(f"[{self.job.id}] FINAL STREAMED RESPONSE (concatenated):\n---\n{final_result}\n---")
        await self.publisher.publish_final_result(self.job.id, final_result, metadata=self.job.metadata)
        return final_result

