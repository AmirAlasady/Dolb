# MS6/app/execution/custom_lrs_llm.py

import httpx
import json
import asyncio
from typing import Any, List, AsyncIterator, Optional, Union
from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
from pydantic import Field
from app.logging_config import logger

class ChatLRS(BaseChatModel):
    """
    Custom LangChain ChatModel for the Local Runtime Service (LRS).
    This version handles both synchronous and asynchronous execution for chat.
    """
    api_url: str
    model_name: str
    
    # Separate clients for sync and async operations
    sync_client: httpx.Client = Field(default=None, exclude=True)
    async_client: httpx.AsyncClient = Field(default=None, exclude=True)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.sync_client = httpx.Client(timeout=300.0)
        self.async_client = httpx.AsyncClient(timeout=300.0)

    def _format_prompt(self, messages: List[BaseMessage]) -> str:
        """
        Converts LangChain messages into a single string prompt.
        This is a generic formatter; specific model logic can be added here.
        """
        prompt_str = ""
        for msg in messages:
            # Helper to robustly get text content
            text_content = ""
            if isinstance(msg.content, str):
                text_content = msg.content
            elif isinstance(msg.content, list):
                text_content = "\n".join(
                    item.get("text", "") for item in msg.content if isinstance(item, dict) and item.get("type") == "text"
                )
            
            if msg.type == "system":
                prompt_str += f"System: {text_content}\n"
            elif msg.type == "human":
                prompt_str += f"User: {text_content}\n"
            elif msg.type == "ai":
                prompt_str += f"Assistant: {text_content}\n"
        
        prompt_str += "Assistant:" # Prompt the model for a response
        return prompt_str

    def _generate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs: Any
    ) -> ChatResult:
        """
        The synchronous generation method for blocking calls.
        """
        prompt = self._format_prompt(messages)
        
        params = self.dict(exclude={"api_url", "model_name", "sync_client", "async_client"})
        params.update(kwargs)
        
        if stop:
            params['stop_sequences'] = stop
            
        payload = {
            "model_name": self.model_name,
            "prompt": prompt,
            "parameters": params,
            "stream": False
        }
        
        response = self.sync_client.post(self.api_url, json=payload)
        response.raise_for_status()
        
        result_json = response.json()
        content = result_json.get("generated_text", "")
        message = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=message)])
    
    def _get_stop_sequences(self) -> List[str]:
        """
        Returns a list of default stop tokens based on the model family.
        The TGI server will use these to stop generation cleanly.
        """
        model_name_lower = self.model_name.lower()
        if "qwen" in model_name_lower:
            return ["<|im_end|>", "<|im_start|>"]
        elif "llama" in model_name_lower or "mistral" in model_name_lower or "tiny" in model_name_lower:
            return ["</s>", "<s>"]
        return []
    
    def _generate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs: Any
    ) -> ChatResult:
        prompt = self._format_prompt(messages)
        
        params = self.dict(exclude={"api_url", "model_name", "sync_client", "async_client"})
        params.update(kwargs)
        
        # --- APPLY THE FIX ---
        # 1. Get the default stop sequences for this model.
        stop_sequences = self._get_stop_sequences()
        # 2. If the user passed in custom stop sequences, add them.
        if stop:
            stop_sequences = list(set(stop_sequences + stop))
        
        # 3. Add the final list to the parameters for TGI.
        if stop_sequences:
            params['stop_sequences'] = stop_sequences
        # --- END OF FIX ---
            
        payload = {"model_name": self.model_name, "prompt": prompt, "parameters": params, "stream": False}
        
        response = self.sync_client.post(self.api_url, json=payload)
        response.raise_for_status()
        
        result_json = response.json()
        content = result_json.get("generated_text", "")

        # --- APPLY THE FIX ---
        # 4. Manually strip any stop tokens from the final output, just in case.
        for seq in (stop_sequences or []):
            if content.endswith(seq):
                content = content[:-len(seq)]
        # --- END OF FIX ---

        message = AIMessage(content=content.strip())
        return ChatResult(generations=[ChatGeneration(message=message)])
    
        
    async def _astream(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        prompt = self._format_prompt(messages)
        params = self.dict(exclude={"api_url", "model_name", "sync_client", "async_client"})
        params.update(kwargs)
        
        # Apply the same stop sequence logic to streaming
        stop_sequences = self._get_stop_sequences()
        if stop:
            stop_sequences = list(set(stop_sequences + stop))
        if stop_sequences:
            params['stop_sequences'] = stop_sequences

        payload = {"model_name": self.model_name, "prompt": prompt, "parameters": params, "stream": True}

        async with self.async_client.stream("POST", self.api_url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line and line.startswith("data:"):
                    try:
                        json_data = json.loads(line[5:])
                        token_text = json_data.get("token", {}).get("text", "")
                        # Defensive check: do not yield the stop token
                        if token_text and token_text not in (stop_sequences or []):
                            yield ChatGenerationChunk(message=AIMessageChunk(content=token_text))
                    except json.JSONDecodeError:
                        continue

    @property
    def _llm_type(self) -> str:
        return "chat_lrs"















"""

# MS6/app/execution/custom_lrs_llm.py
import json
import httpx
import asyncio
from typing import Any, List, AsyncIterator, Optional, Union, Tuple
from copy import deepcopy

from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
from pydantic import Field

from app.logging_config import logger


class ChatLRS(BaseChatModel):

    api_url: str
    model_name: str

    sync_client: httpx.Client = Field(default=None, exclude=True)
    async_client: httpx.AsyncClient = Field(default=None, exclude=True)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        if self.sync_client is None:
            self.sync_client = httpx.Client(timeout=300.0)
        if self.async_client is None:
            self.async_client = httpx.AsyncClient(timeout=300.0)

    def _get_stop_sequences(self) -> List[str]:
        name = self.model_name.lower()
        if "qwen" in name:
            return ["<|im_end|>", "<|im_start|>"]
        if "llama" in name or "mistral" in name or "tiny" in name:
            return ["</s>", "<s>", "[INST]", "[/INST]"]
        return []

    def _format_prompt(self, messages: List[BaseMessage]) -> str:
        model_name_lower = self.model_name.lower()

        def extract_text_from_content(content: Union[str, List[dict]]) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            return ""

        if "qwen" in model_name_lower:
            system_prompt = ""
            user_and_ai_messages = []
            for msg in messages:
                if msg.type == "system":
                    system_prompt = extract_text_from_content(msg.content)
                else:
                    user_and_ai_messages.append(msg)
            prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            for msg in user_and_ai_messages:
                role = "user" if msg.type == "human" else "assistant"
                text_content = extract_text_from_content(msg.content)
                prompt += f"<|im_start|>{role}\n{text_content}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"
            return prompt
        else:
            prompt = "<s>"
            system_prompt = ""
            msgs = list(messages)
            if msgs and msgs[0].type == "system":
                system_prompt = extract_text_from_content(msgs[0].content)
                msgs = msgs[1:]
            for i in range(0, len(msgs), 2):
                user_msg = msgs[i]
                text_content = extract_text_from_content(user_msg.content)
                if i == 0 and system_prompt:
                    prompt += f"[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\n{text_content} [/INST]"
                else:
                    prompt += f"[INST] {text_content} [/INST]"
                if i + 1 < len(msgs):
                    ai_msg = msgs[i + 1]
                    ai_content = extract_text_from_content(ai_msg.content)
                    prompt += f" {ai_content} </s>"
                    if i + 2 < len(msgs):
                        prompt += "<s>"
            return prompt

    # --- bind tools ---
    def bind_tools(self, tools: List[Any]) -> "ChatLRS":
        try:
            new = self.copy(deep=False)
            setattr(new, "_bound_tools", tools)
            logger.info(f"bind_tools: attached {len(tools)} tool(s) to shallow copy of LLM.")
            return new
        except Exception as e:
            logger.warning(f"bind_tools: shallow copy failed ({e}); attaching tools to original instance.")
            setattr(self, "_bound_tools", tools)
            return self

    @property
    def bound_tools(self) -> Optional[List[Any]]:
        return getattr(self, "_bound_tools", None)

    # ---- parsing helpers (kept from your code) ----
    def _parse_tool_calls_from_structured(self, tool_calls_from_model: Any) -> Optional[List[dict]]:
        if not tool_calls_from_model:
            return None
        if not isinstance(tool_calls_from_model, list):
            if isinstance(tool_calls_from_model, dict):
                tool_calls_from_model = [tool_calls_from_model]
            else:
                return None
        formatted = []
        for call in tool_calls_from_model:
            if not isinstance(call, dict):
                continue
            fn = call.get("function")
            if isinstance(fn, dict):
                name = fn.get("name")
                args_raw = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else fn.get("arguments", {}) or {}
                except Exception:
                    args = {"_raw": args_raw}
            else:
                name = call.get("name") or call.get("tool") or call.get("tool_name")
                args = call.get("args") or call.get("tool_input") or call.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"_raw": args}
            formatted.append({"name": name, "args": args or {}, "id": call.get("id")})
        return formatted if formatted else None

    def _parse_tool_calls_from_content_json(self, content: str) -> Optional[List[dict]]:
        if not content:
            return None
        text = content.strip()
        if not (text.startswith("[") or text.startswith("{")):
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return None

        if isinstance(parsed, dict):
            parsed = [parsed]

        if not isinstance(parsed, list):
            return None

        calls = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = item.get("tool") or item.get("name")
            args = item.get("tool_input") or item.get("args") or item.get("arguments")
            fn = item.get("function")
            if fn:
                if isinstance(fn, dict):
                    name = name or fn.get("name")
                    raw_args = fn.get("arguments", "{}")
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except Exception:
                            args = {"_raw": raw_args}
                    else:
                        args = raw_args
                elif isinstance(fn, str):
                    name = name or fn
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"_raw": args}
            args = args or {}
            calls.append({"name": name, "args": args, "id": item.get("id")})
        return calls if calls else None

    def _extract_content_and_toolcalls_from_response(self, result_json: Any) -> Tuple[str, Optional[List[dict]]]:
        content = ""
        tool_calls = None

        # top-level list
        if isinstance(result_json, list):
            try:
                if all(isinstance(it, dict) for it in result_json):
                    maybe = self._parse_tool_calls_from_content_json(json.dumps(result_json))
                    if maybe:
                        return ("", maybe)
                content = json.dumps(result_json)
                return (content, None)
            except Exception:
                return (str(result_json), None)

        # choices style
        if isinstance(result_json, dict) and "choices" in result_json:
            try:
                choice = (result_json.get("choices") or [])[0] or {}
                message_obj = choice.get("message") or {}
                content = message_obj.get("content") or ""
                tool_calls_from_model = message_obj.get("tool_calls") or message_obj.get("function_call") or message_obj.get("function_calls")
                structured = self._parse_tool_calls_from_structured(tool_calls_from_model)
                if structured:
                    return ("", structured)
                parsed_from_content = self._parse_tool_calls_from_content_json(content)
                if parsed_from_content:
                    return ("", parsed_from_content)
                return (content or "", None)
            except Exception:
                return (json.dumps(result_json), None)

        # common top-level keys
        if isinstance(result_json, dict):
            for key in ("output", "outputs", "response", "result", "text", "content"):
                if key in result_json:
                    val = result_json.get(key)
                    if isinstance(val, (list, dict)):
                        parsed_tool_calls = None
                        if isinstance(val, list) and all(isinstance(x, dict) for x in val):
                            parsed_tool_calls = self._parse_tool_calls_from_content_json(json.dumps(val))
                        elif isinstance(val, dict):
                            parsed_tool_calls = self._parse_tool_calls_from_content_json(json.dumps(val)) or self._parse_tool_calls_from_structured(val.get("tool_calls") if isinstance(val, dict) else None)
                        if parsed_tool_calls:
                            return ("", parsed_tool_calls)
                        try:
                            content = json.dumps(val) if not isinstance(val, str) else val
                        except Exception:
                            content = str(val)
                        return (content or "", None)
            # maybe dict itself is tool-calls-body
            maybe_list = None
            try:
                maybe_list = self._parse_tool_calls_from_content_json(json.dumps(result_json))
            except Exception:
                maybe_list = None
            if maybe_list:
                return ("", maybe_list)
            try:
                return (json.dumps(result_json), None)
            except Exception:
                return (str(result_json), None)

        # fallback
        return (str(result_json), None)

    def _normalize_tool_calls_for_agent(self, parsed_calls: List[dict]) -> List[dict]:
        normalized = []
        for c in parsed_calls:
            name = c.get("name") or c.get("tool") or c.get("function")
            args = c.get("args") or c.get("arguments") or c.get("tool_input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"_raw": args}
            args = args or {}
            entry = {
                "name": name,
                "args": args,
                "tool": name,
                "tool_input": args,
                "id": c.get("id")
            }
            normalized.append(entry)
        return normalized

    # helper: create a ChatResult robustly across langchain_core versions
    def _safe_chatresult_from_ai_message(self, message: AIMessage) -> ChatResult:

        e_primary = e_parse1 = e_parse2 = e_parse3 = e_last = None

        # Try direct constructor with ChatGeneration(message=AIMessage(...))
        try:
            return ChatResult(generations=[[ChatGeneration(message=message)]])
        except Exception as exc:
            e_primary = exc
            logger.debug("ChatResult(primary ctor) failed: %s", e_primary)

        # Candidate 1: nested 'message' dict with content + type + additional_kwargs
        try:
            msg_type = getattr(message, "type", "assistant") or "assistant"
            parsed1 = {
                "generations": [
                    [
                        {
                            "message": {
                                "content": message.content or "",
                                "type": msg_type,
                                "additional_kwargs": {}
                            }
                        }
                    ]
                ]
            }
            return ChatResult.parse_obj(parsed1)
        except Exception as exc:
            e_parse1 = exc
            logger.debug("ChatResult.parse_obj(candidate1) failed: %s", e_parse1)

        # Candidate 2: nested message with content as object (some versions use content.text)
        try:
            parsed2 = {
                "generations": [
                    [
                        {
                            "message": {
                                "content": {"text": message.content or ""},
                                "type": getattr(message, "type", "assistant") or "assistant",
                                "additional_kwargs": {}
                            }
                        }
                    ]
                ]
            }
            return ChatResult.parse_obj(parsed2)
        except Exception as exc:
            e_parse2 = exc
            logger.debug("ChatResult.parse_obj(candidate2) failed: %s", e_parse2)

        # Candidate 3: legacy text-only shape
        try:
            parsed3 = {"generations": [[{"text": message.content or ""}]]}
            return ChatResult.parse_obj(parsed3)
        except Exception as exc:
            e_parse3 = exc
            logger.debug("ChatResult.parse_obj(candidate3=text) failed: %s", e_parse3)

        # Candidate 4: attempt to build ChatGeneration via parse_obj then wrap
        try:
            # try to coerce a ChatGeneration dict that some versions accept
            gen_like = {"message": {"content": message.content or "", "type": getattr(message, "type", "assistant") or "assistant"}}
            chatgen = None
            try:
                chatgen = ChatGeneration.parse_obj(gen_like)
            except Exception:
                # some versions require 'text' instead
                chatgen = ChatGeneration.parse_obj({"text": message.content or ""})
            return ChatResult(generations=[[chatgen]])
        except Exception as exc:
            e_last = exc
            logger.exception("Unable to build ChatResult in any known shape: %s / %s / %s / %s / %s", e_primary, e_parse1, e_parse2, e_parse3, e_last)
            # Final fallback: raise so the caller can detect irrecoverable failure
            raise

    # -------------------------
    # Core internal generator (non-streaming) â€” tries multiple request shapes
    # -------------------------
    def _generate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs: Any
    ) -> ChatResult:
        # Build the chat prompt string
        prompt = self._format_prompt(messages)

        params = kwargs
        model_params = self.dict(exclude={"api_url", "model_name", "sync_client", "async_client"})
        params.update(model_params)
        if stop:
            params['stop_sequences'] = stop

        # Candidate payload shapes to try (in order)
        tries = [
            {"model_name": self.model_name, "inputs": prompt, "parameters": params, "stream": False},
            {"model_name": self.model_name, "inputs": [prompt], "parameters": params, "stream": False},
            {"model_name": self.model_name, "prompt": prompt, "parameters": params, "stream": False},
            {"model_name": self.model_name, "input": prompt, "parameters": params, "stream": False},
            {"model_name": self.model_name, "instances": [{"input": prompt}], "parameters": params, "stream": False},
            {"model_name": self.model_name, "messages": [{"role": "user", "content": prompt}], "parameters": params, "stream": False},
        ]

        last_exc = None
        for idx, payload in enumerate(tries):
            # small trimmed preview log
            try:
                preview = json.dumps(payload, ensure_ascii=False)[:4000]
            except Exception:
                preview = str(payload)[:4000]
            logger.info("ChatLRS._generate: try %d POST payload preview (trimmed 4k): %s", idx + 1, preview)

            try:
                response = self.sync_client.post(self.api_url, json=payload)
            except Exception as exc:
                last_exc = exc
                logger.exception("ChatLRS._generate: POST attempt %d failed to send: %s", idx + 1, exc)
                continue

            # if non-2xx, log body and continue to next payload shape if this looks like a schema mismatch
            if response.status_code >= 400:
                body = "<unreadable>"
                try:
                    body = response.text
                except Exception:
                    pass
                logger.error("ChatLRS._generate: attempt %d received non-2xx (%s): %s", idx + 1, response.status_code, body[:8000])

                last_exc = Exception(f"HTTP {response.status_code}: {body[:4000]}")
                # try next candidate
                continue

            # success-ish: parse
            try:
                result_json = response.json()
            except Exception:
                result_json = response.text

            content, parsed_tool_calls = self._extract_content_and_toolcalls_from_response(result_json)

            # Attach tool calls if present
            if parsed_tool_calls:
                norm = self._normalize_tool_calls_for_agent(parsed_tool_calls)
                msg = AIMessage(content="")
                # attach tool_calls to message in the shape agent expects
                setattr(msg, "tool_calls", norm)
                logger.info("ChatLRS._generate: parsed %d tool_call(s) and attached to AIMessage.", len(norm))
                return self._safe_chatresult_from_ai_message(msg)

            # otherwise textual content: return ChatResult containing the text
            msg = AIMessage(content=content or "")
            return self._safe_chatresult_from_ai_message(msg)

        # if all tries failed
        err_text = f"LLM backend error: all request shapes failed. Last exception: {str(last_exc)}"
        logger.error("ChatLRS._generate: %s", err_text)
        return self._safe_chatresult_from_ai_message(AIMessage(content=err_text))

    # -------------------------
    # Public entrypoints
    # -------------------------
    def generate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any
    ) -> ChatResult:
        try:
            res = self._generate(messages, stop=stop, **kwargs)
            if isinstance(res, ChatResult):
                return res
        except Exception as e:
            logger.exception("ChatLRS.generate: internal _generate raised: %s", e)
            return self._safe_chatresult_from_ai_message(AIMessage(content=str(e)))

        # fallback coercion (shouldn't normally happen)
        try:
            content, parsed_tool_calls = self._extract_content_and_toolcalls_from_response(res)
        except Exception:
            try:
                content = json.dumps(res)
            except Exception:
                content = str(res)
            parsed_tool_calls = None

        if parsed_tool_calls:
            msg = AIMessage(content="")
            msg.tool_calls = self._normalize_tool_calls_for_agent(parsed_tool_calls)
            return self._safe_chatresult_from_ai_message(msg)
        return self._safe_chatresult_from_ai_message(AIMessage(content=content or ""))

    async def agenerate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any
    ) -> ChatResult:
        try:
            res = await self._agenerate(messages, stop=stop, **kwargs)
            if isinstance(res, ChatResult):
                return res
        except Exception as e:
            logger.exception("ChatLRS.agenerate: internal _agenerate raised: %s", e)
            return self._safe_chatresult_from_ai_message(AIMessage(content=str(e)))

        try:
            content, parsed_tool_calls = self._extract_content_and_toolcalls_from_response(res)
        except Exception:
            try:
                content = json.dumps(res)
            except Exception:
                content = str(res)
            parsed_tool_calls = None

        if parsed_tool_calls:
            msg = AIMessage(content="")
            msg.tool_calls = self._normalize_tool_calls_for_agent(parsed_tool_calls)
            return self._safe_chatresult_from_ai_message(msg)
        return self._safe_chatresult_from_ai_message(AIMessage(content=content or ""))

    async def _agenerate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs: Any
    ) -> ChatResult:
        prompt = self._format_prompt(messages)
        params = kwargs
        model_params = self.dict(exclude={"api_url", "model_name", "sync_client", "async_client"})
        params.update(model_params)
        if stop:
            params['stop_sequences'] = stop

        # try async shapes similar to synchronous tries
        tries = [
            {"model_name": self.model_name, "inputs": prompt, "parameters": params, "stream": False},
            {"model_name": self.model_name, "prompt": prompt, "parameters": params, "stream": False},
            {"model_name": self.model_name, "input": prompt, "parameters": params, "stream": False},
            {"model_name": self.model_name, "messages": [{"role": "user", "content": prompt}], "parameters": params, "stream": False},
        ]

        last_body = None
        for payload in tries:
            try:
                preview = json.dumps(payload, ensure_ascii=False)[:4000]
            except Exception:
                preview = str(payload)[:4000]
            logger.info("ChatLRS._agenerate: POST payload preview (trimmed 4k): %s", preview)

            async with self.async_client.stream("POST", self.api_url, json=payload) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    body = body.decode(errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
                    logger.error("ChatLRS._agenerate: non-2xx (%s): %s", response.status_code, body[:8000])
                    last_body = body
                    continue
                text = await response.aread()
                try:
                    result_json = json.loads(text)
                except Exception:
                    result_json = text.decode() if isinstance(text, (bytes, bytearray)) else str(text)

            content, parsed_tool_calls = self._extract_content_and_toolcalls_from_response(result_json)
            if parsed_tool_calls:
                msg = AIMessage(content="")
                msg.tool_calls = self._normalize_tool_calls_for_agent(parsed_tool_calls)
                return self._safe_chatresult_from_ai_message(msg)
            return self._safe_chatresult_from_ai_message(AIMessage(content=content or ""))

        err_text = f"LLM backend async error: all request shapes failed. Last body: {last_body}"
        logger.error(err_text)
        return self._safe_chatresult_from_ai_message(AIMessage(content=err_text))

    async def _astream(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        prompt = self._format_prompt(messages)
        params = kwargs
        model_params = self.dict(exclude={"api_url", "model_name", "sync_client", "async_client"})
        params.update(model_params)
        stop_sequences = self._get_stop_sequences()
        if stop:
            stop_sequences = list(set(stop_sequences + stop))
        if stop_sequences:
            params['stop_sequences'] = stop_sequences

        payload = {"model_name": self.model_name, "prompt": prompt, "parameters": params, "stream": True}

        async with self.async_client.stream("POST", self.api_url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line and line.startswith("data:"):
                    try:
                        json_data = json.loads(line[5:])
                        token_text = json_data.get("token", {}).get("text", "")
                        if token_text and token_text not in (stop_sequences or []):
                            message_chunk = AIMessageChunk(content=token_text)
                            generation_chunk = ChatGenerationChunk(message=message_chunk)
                            yield generation_chunk
                            if run_manager:
                                await run_manager.on_llm_new_token(token_text, chunk=generation_chunk)
                    except json.JSONDecodeError:
                        continue

    # Make the instance callable and alias to generate for compatibility
    def __call__(self, messages: List[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        return self.generate(messages, *args, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "chat_lrs"
"""

