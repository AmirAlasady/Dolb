from django.db import transaction
from ..models import Edge, EdgeType, FFI, FFO, FBI, FBO, Projection
from .errors import EdgeNotFound, SelfLoopNotAllowed


class EdgeRepository:

    def create_edge(self, graph_id, source_node_id, dest_node_id,
                    edge_type: str = EdgeType.FORWARD) -> Edge:
        """
        Creates an Edge and auto-provisions the correct wiring buffers:
          - FORWARD  → FFO + FFI + base FFI Projection
          - FEEDBACK → FBO + FBI + base FBI Projection (~X[raw])

        The edge_type is determined by the service layer (via BFS),
        not set by the caller directly in most cases.
        """
        if source_node_id == dest_node_id:
            raise SelfLoopNotAllowed("Self-loops are not allowed.")

        with transaction.atomic():
            edge, _created = Edge.objects.get_or_create(
                graph_id=graph_id,
                source_node_id=source_node_id,
                dest_node_id=dest_node_id,
                defaults={'edge_type': edge_type},
            )

            if not _created:
                # Edge already existed — buffers already provisioned. Return as-is.
                return edge

            if edge_type == EdgeType.FORWARD:
                # --- Forward wiring (original behaviour, unchanged) ---
                FFO.objects.get_or_create(
                    graph_id=graph_id,
                    owner_node_id=source_node_id,
                    dest_node_id=dest_node_id,
                )
                ffi, _ = FFI.objects.get_or_create(
                    graph_id=graph_id,
                    owner_node_id=dest_node_id,
                    source_node_id=source_node_id,
                )
                # Base (non-selectable) projection: A[raw]
                Projection.objects.get_or_create(
                    graph_id=graph_id,
                    owner_node_id=dest_node_id,
                    ffi=ffi,
                    fbi=None,
                    created_by_rule=None,
                    defaults={'op': None},
                )

            else:
                # --- Feedback wiring (new) ---
                FBO.objects.get_or_create(
                    graph_id=graph_id,
                    owner_node_id=source_node_id,
                    dest_node_id=dest_node_id,
                )
                fbi, _ = FBI.objects.get_or_create(
                    graph_id=graph_id,
                    owner_node_id=dest_node_id,
                    source_node_id=source_node_id,
                )
                # Base (non-selectable) projection: ~ControllerName[raw]
                Projection.objects.get_or_create(
                    graph_id=graph_id,
                    owner_node_id=dest_node_id,
                    ffi=None,
                    fbi=fbi,
                    created_by_rule=None,
                    defaults={'op': None},
                )

            return edge

    def delete_edge(self, edge_id):
        """
        Deletes an edge and all its associated wiring buffers and projections.
        Relies on Edge.delete() which handles both FORWARD and FEEDBACK cleanup.
        """
        try:
            edge = Edge.objects.get(id=edge_id)
        except Edge.DoesNotExist:
            raise EdgeNotFound(f"Edge {edge_id} not found.")

        # Edge.delete() handles the cascade for both edge types
        edge.delete()

    def list_edges(self, graph_id) -> list[Edge]:
        return list(Edge.objects.filter(graph_id=graph_id).select_related(
            'source_node', 'dest_node'
        ))
