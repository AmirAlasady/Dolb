from django.db import transaction
from rest_framework.exceptions import ValidationError

from .security import SecurityService, RequestContext
from .exceptions import ResourceNotFound
from .exceptions import ResourceNotFound
from ..models import Graph, GNode


class GraphService:
    def __init__(self, graph_repo=None, security: SecurityService | None = None):
        self.graph_repo = graph_repo  # optional
        self.security = security or SecurityService()

    def _get_graph_or_404(self, graph_id) -> Graph:
        try:
            if self.graph_repo:
                return self.graph_repo.get_graph(graph_id)
            # fall safe back to ORM if no repo provided
            return Graph.objects.get(id=graph_id)
        except Graph.DoesNotExist:
            raise ResourceNotFound(f"Graph {graph_id} not found.")

    @transaction.atomic
    def create_graph(self, ctx: RequestContext, *, project_id, name, description=None) -> Graph:
        # Security: must own/have access to project in MS2
        self.security.assert_project_access(ctx, project_id)

        if not name or not name.strip():
            raise ValidationError("Graph name is required.")

        if self.graph_repo:
            return self.graph_repo.create_graph(project_id=project_id, name=name.strip(), description=description)

        return Graph.objects.create(
            project_id=project_id,
            name=name.strip(),
            description=description,
        )

    def get_graph(self, ctx: RequestContext, graph_id) -> Graph:
        g = self._get_graph_or_404(graph_id)
        self.security.assert_project_access(ctx, g.project_id)
        return g

    def list_graphs_for_project(self, ctx: RequestContext, project_id):
        self.security.assert_project_access(ctx, project_id)
        if self.graph_repo:
            return self.graph_repo.list_graphs(project_id)
        return Graph.objects.filter(project_id=project_id).order_by("-updated_at")

    @transaction.atomic
    def update_graph(self, ctx: RequestContext, graph_id, *, name=None, description=None) -> Graph:
        g = self._get_graph_or_404(graph_id)
        self.security.assert_project_access(ctx, g.project_id)

        if name is not None:
            if not name.strip():
                raise ValidationError("Graph name cannot be empty.")
            g.name = name.strip()
        if description is not None:
            g.description = description

        g.save()
        return g

    @transaction.atomic
    def delete_graph(self, ctx: RequestContext, graph_id):
        g = self._get_graph_or_404(graph_id)
        self.security.assert_project_access(ctx, g.project_id)

        # 1. Fetch all nodes in this graph that have an MS4 link
        linked_nodes = GNode.objects.filter(graph_id=graph_id, ms4_node_id__isnull=False)

        # 2. Unclaim each from MS4
        for node in linked_nodes:
            self.security.node_client.unclaim_node(ctx.jwt_token, str(node.ms4_node_id))

        # 3. Cascade delete is fine (you chose it). This will delete all nodes/edges/etc.
        g.delete()

    @transaction.atomic
    def delete_graphs_for_project(self, ctx: RequestContext, project_id):
        # For project deletion, we assume MS4 is also cleaning up its nodes (via its own consumer).
        # We generally don't have a user JWT here to call 'unclaim' anyway.
        # So we just delete the local graphs.
        
        graphs = Graph.objects.filter(project_id=project_id)
        count = graphs.count()
        graphs.delete()
        
        return count, 0  # 0 unclaimed
