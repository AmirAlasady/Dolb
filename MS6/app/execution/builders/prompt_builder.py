# MS6/app/execution/builders/prompt_builder.py
"""
from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

class PromptBuilder(BaseBuilder):

    async def build(self, context: BuildContext) -> BuildContext:
        job = context.job
        logger.info(f"[{job.id}] PromptBuilder: Assembling final prompt...")
        
        model_capabilities = job.model_config.get("capabilities", [])
        
        # This list will hold all parts of the user's turn for the multimodal prompt
        user_content_blocks = []
        # This string will hold the combined text for the memory service
        combined_text_for_memory = job.prompt_text

        # 1. Start with the user's primary text prompt.
        if job.prompt_text:
            user_content_blocks.append({"type": "text", "text": job.prompt_text})
            
        # 2. Process content from on-the-fly files (e.g., images, docs).
        if context.on_the_fly_data:
            text_parts_files = []
            image_parts = []

            for data in context.on_the_fly_data:
                content_type = data.get("type")
                if content_type == "text_content":
                    text_parts_files.append(data.get('content', ''))
                elif content_type == "image_url":
                    if "image" in model_capabilities:
                        image_parts.append({"type": "image_url", "image_url": {"url": data.get("url")}})
                    else:
                        logger.warning(f"[{job.id}] Model does not support images; ignoring image input.")
            
            # Combine all extracted text from files into a single context block
            if text_parts_files:
                combined_text_from_files = "\n\n".join(text_parts_files)
                context_header = "\n\n--- Content from Provided Files ---\n"
                full_text_context = context_header + combined_text_from_files
                
                user_content_blocks.append({"type": "text", "text": full_text_context})
                combined_text_for_memory += full_text_context

            # Add any valid image parts to the prompt
            user_content_blocks.extend(image_parts)

        # 3. Process RAG context and build the final system instruction.
        system_instruction = "You are a helpful and intelligent AI assistant."
        
        # The job.rag_docs is now correctly a list of chunk dictionaries
        if job.rag_docs:
            logger.info(f"[{job.id}] RAG context found with {len(job.rag_docs)} chunks. Injecting forceful prompt instructions.")
            
            rag_context_parts = [chunk.get('content', '') for chunk in job.rag_docs]
            combined_rag_context = "\n\n---\n\n".join(rag_context_parts)
            
            # This forceful prompt overrides the default system message.
            system_instruction = (
                "You are a helpful assistant. Answer the user's question based ONLY on the following context. "
                "Do not use any of your outside knowledge. If the answer is not found in the context, "
                "state that you could not find the information in the provided documents.\n\n"
                "--- CONTEXT ---\n"
                f"{combined_rag_context}\n"
                "--- END CONTEXT ---"
            )
        
        # 4. Assemble the final messages list for the ChatPromptTemplate.
        human_message_turn = HumanMessage(content=user_content_blocks)
        messages_for_template = [SystemMessage(content=system_instruction)]
        
        if context.memory:
            messages_for_template.append(MessagesPlaceholder(variable_name="chat_history"))+
        
        messages_for_template.append(human_message_turn)
        
        if context.tools:
            messages_for_template.append(MessagesPlaceholder(variable_name="agent_scratchpad"))
            
        context.prompt_template = ChatPromptTemplate(messages=messages_for_template)
        
        # 5. Populate final_input with the combined text string. This is crucial
        #    for the 'persist_inputs_in_memory' feature.
        context.final_input = {"input": combined_text_for_memory}
        
        logger.info(f"[{job.id}] PromptBuilder: Assembly complete.")
        return context
    
"""
# MS6/app/execution/builders/prompt_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.prompts import PromptTemplate
class PromptBuilder(BaseBuilder):
    """
    Assembles the final prompt. This definitive version correctly handles all
    combinations of RAG, tools, and multimodal inputs by creating a single,
    unified system prompt, while preserving the logic for memory persistence.
    """
    async def build(self, context: BuildContext) -> BuildContext:
        job = context.job
        logger.info(f"[{job.id}] PromptBuilder: Assembling final prompt...")
        
        model_capabilities = job.model_config.get("capabilities", [])
        
        # This is your existing, correct logic for building the user's turn
        # and the combined text for memory persistence. It is preserved.
        user_content_blocks = []
        combined_text_for_memory = job.prompt_text

        if job.prompt_text:
            user_content_blocks.append({"type": "text", "text": job.prompt_text})
            
        if context.on_the_fly_data:
            text_parts_files = []
            image_parts = []

            for data in context.on_the_fly_data:
                content_type = data.get("type")
                if content_type == "text_content":
                    text_parts_files.append(data.get('content', ''))
                elif content_type == "image_url":
                    if "image" in model_capabilities:
                        image_parts.append({"type": "image_url", "image_url": {"url": data.get("url")}})
                    else:
                        logger.warning(f"[{job.id}] Model does not support images; ignoring image input.")
            
            if text_parts_files:
                combined_text_from_files = "\n\n".join(text_parts_files)
                context_header = "\n\n--- Content from Provided Files ---\n"
                full_text_context = context_header + combined_text_from_files
                
                user_content_blocks.append({"type": "text", "text": full_text_context})
                combined_text_for_memory += full_text_context

            user_content_blocks.extend(image_parts)

        # --- THE DEFINITIVE, UNIFIED SYSTEM PROMPT LOGIC ---
        # 1. Start with the base persona.
        system_instruction = "You are a helpful and intelligent AI assistant."
        if context.tools and getattr(context.llm, '_llm_type', None) == 'chat_lrs':
            logger.info(f"[{job.id}] Tools detected for LRS model. Injecting custom agent system prompt.")

            # A. Manually format the tools into a clean, readable string.
            formatted_tools = ""
            for tool in context.tools:
                # By adding an extra set of braces {{...}}, we tell the f-string to treat them as literal characters.
                schema_as_string = tool.args_schema.schema_json(indent=2)
                formatted_tools += f"- Tool Name: {tool.name}\n"
                formatted_tools += f"  Description: {tool.description}\n"
                formatted_tools += f"  Arguments Schema: {schema_as_string}\n\n"
                
            system_instruction += f""" and you have access to a set of tools. 
Use these tools to answer the user's questions.
The tools you can use are described below as: 
{formatted_tools}

When you decide to use a tool, you MUST follow the Output Format Rules exactly.

**Output Format Rules (Strict):**

1.  **To Call a Tool:** If you decide to use a tool, 
you MUST respond with **only** a tool call request token **<|tool_call|>** and then in a new line followed by a
 JSON list containing one or more tool call objects. Do not add any other text, explanation, or markdown formatting before or after the JSON.
    The format for a tool call object is: `{{"tool": "<tool_name>", "tool_input": {{"arg_name": "arg_value"}}}}`

    **CORRECT EXAMPLE (Tool Call):**
    <|tool_call|>
    ```json
    [
      {{
        "tool": "find_information_on_web",
        "tool_input": {{
          "query": "latest news about Tesla"
        }}
      }}
    ]
    ```

2.  **To Respond Directly:** If you do not need to use a tool, or if you have already used a tool and have the final answer, respond normally in natural language. Do NOT use the JSON format.
To Respond to the User: If you have the final answer, just respond in plain text
    **CORRECT EXAMPLE (Final Answer):**
    The latest news about Tesla is that their stock price has increased by 5% today.

**Decision Process:**

1.  Analyze the user's request in the context of the conversation.
2.  Check if any tool in `TOOLS AVAILABLE` can directly answer the request.
3.  If a tool is a perfect match, call it immediately by responding with the required JSON.
4.  If no tool is a perfect match, answer from your own knowledge.
5.  After a tool is called and you receive the results, use that information to formulate your final answer to the user in natural language.
"""


        # 2. Check for RAG context.
        #    Your Job class correctly sets job.rag_docs to a list of chunks.
        if job.rag_docs:
            logger.info(f"[{job.id}] RAG context found with {len(job.rag_docs)} chunks. Injecting RAG instructions.")
            
            rag_context_parts = [chunk.get('content', '') for chunk in job.rag_docs]
            combined_rag_context = "\n\n---\n\n".join(rag_context_parts)
            
            # 3. APPEND (do not replace) the RAG instructions to the system message.
            #    This allows LangChain's agent logic to add its own tool instructions later.
            rag_instruction_block = (
                "\n\n--- IMPORTANT INSTRUCTIONS ---\n"
                "You MUST use the following context to answer the user's question. "
                "Do not use your outside knowledge for this part of the request. "
                "If the information is not in the context, explicitly state that you could not find it in the provided documents.\n\n"
                "--- CONTEXT ---\n"
                f"{combined_rag_context}\n"
                "--- END CONTEXT ---"
            )
            system_instruction += rag_instruction_block
        # --- END OF UNIFIED PROMPT LOGIC ---

        # 4. Assemble the final messages list, using your original structure.
        human_message_turn = HumanMessage(content=user_content_blocks)
        #logger.info(f"[{job.id}] full system prompt====>_ {system_instruction}.")
        messages_for_template = [SystemMessage(content=system_instruction)]
        
        if context.memory:
            messages_for_template.append(MessagesPlaceholder(variable_name="chat_history"))

        messages_for_template.append(human_message_turn)

        if context.tools:
            messages_for_template.append(MessagesPlaceholder(variable_name="agent_scratchpad"))
        

        context.prompt_template = ChatPromptTemplate(messages=messages_for_template)
        
        # 5. Populate final_input with the combined text string, preserving your
        #    'persist_inputs_in_memory' feature. This is also preserved from your original code.
        context.final_input = {"input": combined_text_for_memory}
        
        logger.info(f"[{job.id}] PromptBuilder: Assembly complete. Final system instruction is {len(system_instruction)} chars long.")
        return context