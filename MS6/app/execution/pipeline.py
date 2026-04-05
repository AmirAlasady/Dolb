from app.execution.build_context import BuildContext
from app.execution.builders.data_builder import DataBuilder
from app.execution.builders.model_builder import ModelBuilder
from app.execution.builders.memory_builder import MemoryBuilder
from app.execution.builders.tool_builder import ToolBuilder
from app.execution.builders.prompt_builder import PromptBuilder

class ChainConstructionPipeline:
    """Orchestrates the step-by-step construction of a runnable LangChain chain."""
    def __init__(self, context: BuildContext):
        self.context = context
        # The order of builders is critical
        self.pipeline = [
            DataBuilder(),
            ModelBuilder(),
            MemoryBuilder(),
            ToolBuilder(), # Now included
            PromptBuilder(),
        ]

    async def run(self) -> BuildContext:
        for builder in self.pipeline:
            self.context = await builder.build(self.context)
        return self.context