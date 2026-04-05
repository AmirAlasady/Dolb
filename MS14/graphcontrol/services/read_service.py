from .security import SecurityService, RequestContext
from .exceptions import ResourceNotFound
from ..models import (
    Graph, GNode, Edge, FFI, FFO, FBI, FBO, Projection, Rule, RuleInput, PromptTemplate
)


class GraphReadService:
    def __init__(self, security: SecurityService | None = None):
        self.security = security or SecurityService()

    def get_graph_snapshot(self, ctx: RequestContext, graph_id) -> dict:
        try:
            graph = Graph.objects.get(id=graph_id)
        except Graph.DoesNotExist:
            raise ResourceNotFound(f"Graph {graph_id} not found.")

        # Security
        self.security.assert_project_access(ctx, graph.project_id)

        # Prefetch smartly (avoid N+1)
        nodes = list(GNode.objects.filter(graph_id=graph_id).order_by("name"))
        edges = list(Edge.objects.filter(graph_id=graph_id).select_related("source_node", "dest_node"))
        ffis = list(FFI.objects.filter(graph_id=graph_id).select_related("owner_node", "source_node"))
        ffos = list(FFO.objects.filter(graph_id=graph_id).select_related("owner_node", "dest_node"))
        fbis = list(FBI.objects.filter(graph_id=graph_id).select_related("owner_node", "source_node"))
        fbos = list(FBO.objects.filter(graph_id=graph_id).select_related("owner_node", "dest_node"))
        projections = list(
            Projection.objects.filter(graph_id=graph_id)
            .select_related("owner_node", "ffi", "ffi__source_node", "fbi", "fbi__source_node", "created_by_rule")
            .prefetch_related("children")
        )
        rules = list(
            Rule.objects.filter(graph_id=graph_id)
            .select_related("owner_node")
            .prefetch_related("outputs", "fbo_outputs")
        )
        rule_inputs = list(RuleInput.objects.filter(rule__graph_id=graph_id).select_related("rule", "projection"))
        templates = list(PromptTemplate.objects.filter(rule__graph_id=graph_id))

        # Return raw objects or serialize as dicts (your choice).
        # For now: return ids + minimal fields (fast + stable).
        return {
            "graph": {
                "id": str(graph.id),
                "project_id": str(graph.project_id),
                "name": graph.name,
                "description": graph.description,
                "created_at": graph.created_at.isoformat(),
                "updated_at": graph.updated_at.isoformat(),
            },
            "nodes": [
                {
                    "id": str(n.id),
                    "name": n.name,
                    "description": getattr(n, "description", None),
                    "node_type": n.node_type,
                    "is_start": n.is_start,
                    "ms4_node_id": str(n.ms4_node_id) if n.ms4_node_id else None,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": str(e.id),
                    "source": str(e.source_node_id),
                    "dest": str(e.dest_node_id),
                    "edge_type": e.edge_type,
                }
                for e in edges
            ],
            "ffis": [
                {"id": str(b.id), "owner": str(b.owner_node_id), "source": str(b.source_node_id)}
                for b in ffis
            ],
            "ffos": [
                {"id": str(b.id), "owner": str(b.owner_node_id), "dest": str(b.dest_node_id)}
                for b in ffos
            ],
            "fbis": [
                {"id": str(b.id), "owner": str(b.owner_node_id), "source": str(b.source_node_id)}
                for b in fbis
            ],
            "fbos": [
                {"id": str(b.id), "owner": str(b.owner_node_id), "dest": str(b.dest_node_id)}
                for b in fbos
            ],
            "projections": [
                {
                    "id": str(p.id),
                    "owner_node": str(p.owner_node_id),
                    "ffi": str(p.ffi_id) if p.ffi_id else None,
                    "fbi": str(p.fbi_id) if p.fbi_id else None,
                    "created_by_rule": str(p.created_by_rule_id) if p.created_by_rule_id else None,
                    "op": p.op,
                    "children": [str(c.id) for c in p.children.all()],
                    "is_selectable": p.is_selectable,
                    "context_family": p.context_family,
                    "display_label": p.display_label,
                }
                for p in projections
            ],
            "rules": [
                {
                    "id": str(r.id),
                    "owner_node": str(r.owner_node_id),
                    "name": r.name,
                    "firing_mode": r.firing_mode,
                    "is_terminal": r.is_terminal,
                    # Forward outputs (FFO)
                    "outputs": [str(o.id) for o in r.outputs.all()],
                    # Feedback outputs (FBO) — controller rules that send results back upstream
                    "fbo_outputs": [str(o.id) for o in r.fbo_outputs.all()],
                    # Loop termination bound (None = infinite, N = force exit after N iterations)
                    "max_iterations": r.max_iterations,
                }
                for r in rules
            ],
            "rule_inputs": [
                {
                    "rule": str(ri.rule_id),
                    "projection": str(ri.projection_id),
                    "position": ri.position,
                }
                for ri in rule_inputs
            ],
            "prompt_templates": [
                {
                    "rule": str(t.rule_id),
                    "template_text": t.template_text,
                    "placeholder_map": t.placeholder_map,
                }
                for t in templates
            ],
        }
