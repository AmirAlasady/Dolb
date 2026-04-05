from __future__ import annotations

from dataclasses import dataclass
from typing import List
from uuid import UUID

from rest_framework.exceptions import PermissionDenied, ValidationError

from graphcontrolinternals.clients import ProjectServiceClient

from ..models import Edge
from ..repositories.edge_repo import EdgeRepository
from ..repositories.graph_repo import GraphRepository


@dataclass
class EdgeService:
    """
    Application service for Edge operations.

    Responsibilities:
    - Enforce user authorization on the Graph via MS2 (Project Service).
    - Delegate topology/wiring creation + deletion policy to the EdgeRepository.
    - Keep a thin orchestration layer (SOLID: services orchestrate, repos persist).
    """
    graph_repo: GraphRepository
    edge_repo: EdgeRepository
    project_client: ProjectServiceClient

    @classmethod
    def build_default(cls) -> "EdgeService":
        return cls(
            graph_repo=GraphRepository(),
            edge_repo=EdgeRepository(),
            project_client=ProjectServiceClient(),
        )

    # -------------------------
    # Internal helpers
    # -------------------------

    def _authorize_graph_access(self, jwt_token: str, graph_id: UUID) -> None:
        """
        Security gate:
        - Load Graph (to get project_id)
        - Ask MS2 if this user can access that project
        """
        graph = self.graph_repo.get_graph(graph_id)

        # MS2 returns 204 on success, otherwise raises DRF exceptions via the client mapper
        self.project_client.check_project_access(jwt_token=jwt_token, project_id=graph.project_id)

    # -------------------------
    # Public API
    # -------------------------

    def create_edge(self, jwt_token: str, graph_id: UUID, source_node_id: UUID, dest_node_id: UUID) -> Edge:
        """
        Classifies the edge automatically:
          - Runs BFS from dest_node following existing FORWARD edges.
          - If source_node is reachable → adding this edge closes a cycle → FEEDBACK.
          - Otherwise → FORWARD (original behaviour).

        Then delegates to the repo which wires up the correct buffer pair
        (FFO/FFI for forward, FBO/FBI for feedback) and a base Projection.
        """
        self._authorize_graph_access(jwt_token, graph_id)

        from ..services.topology_utils import is_reachable_via_forward_edges
        from ..models import EdgeType

        # BFS: if dest can reach source via existing forward edges, this edge closes a cycle.
        creates_cycle = is_reachable_via_forward_edges(
            graph_id=graph_id,
            start_node_id=dest_node_id,
            target_node_id=source_node_id,
        )
        edge_type = EdgeType.FEEDBACK if creates_cycle else EdgeType.FORWARD

        return self.edge_repo.create_edge(
            graph_id=graph_id,
            source_node_id=source_node_id,
            dest_node_id=dest_node_id,
            edge_type=edge_type,
        )


    def delete_edge(self, jwt_token: str, edge_id: UUID) -> None:
        """
        Deletes edge + wiring (FFO/FFI) according to repo policy.
        If you are using CASCADE deletions, dependent projections/ruleinputs will drop too.
        """
        # Need graph_id for authorization: fetch edge first (cheap select_related in repo version if you want)
        edge = Edge.objects.only("id", "graph_id").get(id=edge_id)
        self._authorize_graph_access(jwt_token, edge.graph_id)

        self.edge_repo.delete_edge(edge_id=edge_id)

    def list_edges(self, jwt_token: str, graph_id: UUID) -> List[Edge]:
        self._authorize_graph_access(jwt_token, graph_id)
        return self.edge_repo.list_edges(graph_id=graph_id)

    def get_edge(self, jwt_token: str, edge_id: UUID) -> Edge:
        edge = Edge.objects.get(id=edge_id)
        self._authorize_graph_access(jwt_token, edge.graph_id)
        return edge
