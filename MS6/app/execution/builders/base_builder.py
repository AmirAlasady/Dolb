# Abstract base class for all builders
from abc import ABC, abstractmethod
from app.execution.build_context import BuildContext

class BaseBuilder(ABC):
    """Abstract base class for all components in the chain construction pipeline."""
    
    @abstractmethod
    async def build(self, context: BuildContext) -> BuildContext:
        """
        Processes the input context, adds its component, and returns the modified context.
        """
        pass