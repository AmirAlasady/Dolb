from abc import ABC, abstractmethod

class BaseCollectionStrategy(ABC):
    """Abstract base class for a resource collection strategy."""
    def __init__(self, user_id: str, node_config: dict):
        self.user_id = user_id
        self.node_config = node_config

    @abstractmethod
    def collect_resources(self) -> dict:
        """
        Collects all necessary resources for an inference job.
        This method must be implemented by all concrete strategies.
        Returns a dictionary of the collected resources.
        """
        pass