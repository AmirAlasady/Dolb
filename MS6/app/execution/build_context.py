from dataclasses import dataclass, field
from langchain_core.language_models import BaseChatModel
from langchain_core.memory import BaseMemory
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from app.execution.job import Job

@dataclass
class BuildContext:
    """Holds the state of the chain construction process. Each builder populates a field."""
    job: Job
    llm: BaseChatModel = None
    memory: BaseMemory = None
    tools: list[BaseTool] = field(default_factory=list)
    prompt_template: ChatPromptTemplate = None
    on_the_fly_data: list[dict] = field(default_factory=list)
    final_input: dict = field(default_factory=dict)