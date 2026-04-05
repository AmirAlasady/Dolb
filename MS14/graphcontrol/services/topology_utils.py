"""
topology_utils.py — Graph reachability helpers for MS14.

Used at edge-creation time to automatically classify an edge as
FORWARD or FEEDBACK (cycle-closing).
"""
from __future__ import annotations

from collections import deque
from uuid import UUID


def is_reachable_via_forward_edges(graph_id: UUID, start_node_id: UUID, target_node_id: UUID) -> bool:
    """
    BFS traversal from `start_node_id` following only FORWARD edges.

    Returns True if `target_node_id` is reachable from `start_node_id`
    through existing forward edges.

    Usage at edge-creation time:
        Adding edge  source → dest
        Call:        is_reachable_via_forward_edges(graph_id, dest, source)
        If True  →   source is reachable from dest  →  adding source→dest closes a cycle
                     ⇒ FEEDBACK edge
        If False →   no cycle formed
                     ⇒ FORWARD edge

    Only FORWARD edges are followed; existing feedback edges are ignored
    so classification remains stable.
    """
    from graphcontrol.models import Edge, EdgeType  # local import to avoid circular refs

    # Quick short-circuit: trivially reachable
    if start_node_id == target_node_id:
        return True

    visited: set[UUID] = set()
    queue: deque[UUID] = deque([start_node_id])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        if current == target_node_id:
            return True

        # Expand neighbours: only follow forward edges out of `current`
        neighbour_ids = (
            Edge.objects
            .filter(
                graph_id=graph_id,
                source_node_id=current,
                edge_type=EdgeType.FORWARD,
            )
            .values_list('dest_node_id', flat=True)
        )
        for nid in neighbour_ids:
            if nid not in visited:
                queue.append(nid)

    return False
