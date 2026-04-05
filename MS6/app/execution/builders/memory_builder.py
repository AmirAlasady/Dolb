# MS6/app/execution/builders/memory_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

class MemoryBuilder(BaseBuilder):
    """
    Formats the conversation history received from the Memory Service
    into a list of LangChain message objects. This version correctly and
    safely parses the rich message format.
    """
    async def build(self, context: BuildContext) -> BuildContext:
        job = context.job
        memory_context = job.memory_context
        
        if not memory_context or not memory_context.get("history"):
            return context

        logger.info(f"[{job.id}] Formatting chat history from Memory Service.")
        
        history_messages: list[BaseMessage] = []
        for msg in memory_context.get("history", []):
            
            # --- THE DEFINITIVE FIX IS HERE ---
            role = msg.get("role")
            content_dict = msg.get("content")
            
            # Safely extract the text content from the 'parts' array
            text_content = ""
            if isinstance(content_dict, list) and content_dict:
                # Find the first part with type 'text' and get its content
                first_text_part = next((part for part in content_dict if part.get("type") == "text"), None)
                if first_text_part:
                    text_content = first_text_part.get("text", "")
            # --- END OF FIX ---
            
            if role == "user":
                history_messages.append(HumanMessage(content=text_content))
            elif role == "assistant":
                history_messages.append(AIMessage(content=text_content))
        
        context.memory = history_messages
        
        logger.info(f"[{job.id}] Formatted {len(history_messages)} messages from history.")
        return context