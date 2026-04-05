from .base_strategy import BaseCollectionStrategy
from .llm_strategy import LLMCollectionStrategy

def get_strategy(node_config: dict) -> BaseCollectionStrategy:
    """Factory function to select the appropriate collection strategy."""
    node_type = node_config.get("configuration", {}).get("node_type")

    if node_type in ["ai_agent", "llm_chat"]:
        return LLMCollectionStrategy
    # elif node_type == "image_diffusion":
    #     return DiffusionCollectionStrategy
    else:
        raise ValueError(f"No collection strategy found for node type: {node_type}")
    

