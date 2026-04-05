from tools.models import Tool, ToolType
from django.db import models

def discover_contextual_tools(query: str, user_id: str, tool_ids: list[str] = None) -> list[dict]:
    """
    Implements the MCP logic. Searches the database for relevant tools
    and optionally filters by a list of specified tool IDs.
    """
    print(f"EXECUTING MCP TOOL: discover_contextual_tools with query='{query}'")
    
    # Base query: Find all standard tools the user has access to (system + their own)
    base_queryset = Tool.objects.filter(
        models.Q(is_system_tool=True) | models.Q(owner_id=user_id),
        tool_type=ToolType.STANDARD
    )

    # If the user specified specific tools in an MCP node, filter by them.
    if tool_ids:
        final_queryset = base_queryset.filter(id__in=tool_ids)
    else:
        # If no specific tools are requested, perform discovery based on the query.
        # This is where a vector search on `definition['description']` would be ideal.
        # For now, we simulate a simple keyword search.
        final_queryset = base_queryset.filter(definition__description__icontains=query)

    # Return the public-facing definitions of the found tools
    return [tool.definition for tool in final_queryset]