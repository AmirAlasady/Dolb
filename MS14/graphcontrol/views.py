from __future__ import annotations

from django.forms import ValidationError
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action

from .serializers import (
    GraphCreateSerializer,
    GraphUpdateSerializer,
    GraphSerializer,
    NodeCreateSerializer,
    NodeUpdateSerializer,
    NodeSerializer,
    EdgeCreateSerializer,
    EdgeSerializer,
    RuleCreateSerializer,
    RuleUpdateSerializer,
    RuleSerializer,
    PromptTemplateSerializer,
    PromptTemplateUpdateSerializer,
    GraphSnapshotSerializer,
    ProjectionSerializer,
    FFOSerializer, FFISerializer,
    FBISerializer, FBOSerializer,
)

from .services.security import RequestContext, SecurityService
from .services.graph_service import GraphService
from .services.node_service import NodeService
from .services.edge_service import EdgeService
from .services.rule_service import RuleService
from .services.prompt_template_service import PromptTemplateService
from .services.read_service import GraphReadService
from .services.ffo_service import FFOService
from .services.ffi_service import FFIService

from .repositories.graph_repo import GraphRepository
from .repositories.node_repo import NodeRepository
from .repositories.edge_repo import EdgeRepository
from .repositories.rule_repo import RuleRepository
from .repositories.prompt_repo import PromptTemplateRepository
from .repositories.projection_repo import ProjectionRepository
from .repositories.ffo_repo import FFORepository
from .repositories.ffi_repo import FFIRepository



# ----------------------------
# Shared helpers
# ----------------------------

def _extract_bearer_token(request) -> str:
    auth = request.headers.get("Authorization", "") or ""
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    # DRF may populate request.auth
    if getattr(request, "auth", None):
        return str(request.auth)
    return ""


def _ctx(request) -> RequestContext:
    """
    Build the RequestContext expected by services.
    (jwt_token is the only *required* field for MS2/MS4 calls)
    """
    return RequestContext(jwt_token=_extract_bearer_token(request))


# ----------------------------
# Graph CRUD
# ----------------------------

class GraphViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    # Services (constructed correctly)
    security = SecurityService()
    graph_service = GraphService(graph_repo=GraphRepository(), security=security)

    def list(self, request):
        """
        GET /graphs/?project_id=...
        """
        project_id = request.query_params.get("project_id")
        if not project_id:
            return Response({"detail": "project_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        graphs = self.graph_service.list_graphs_for_project(_ctx(request), project_id)
        return Response(GraphSerializer(graphs, many=True).data)

    def retrieve(self, request, pk=None):
        graph = self.graph_service.get_graph(_ctx(request), pk)
        return Response(GraphSerializer(graph).data)

    def create(self, request):
        s = GraphCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        graph = self.graph_service.create_graph(
            _ctx(request),
            project_id=s.validated_data["project_id"],
            name=s.validated_data["name"],
            description=s.validated_data.get("description"),
        )
        return Response(GraphSerializer(graph).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        s = GraphUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)

        graph = self.graph_service.update_graph(
            _ctx(request),
            pk,
            name=s.validated_data.get("name"),
            description=s.validated_data.get("description"),
        )
        return Response(GraphSerializer(graph).data)

    def destroy(self, request, pk=None):
        self.graph_service.delete_graph(_ctx(request), pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ----------------------------
# Node CRUD (+ attach/detach ms4_node_id)
# ----------------------------

class NodeViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    security = SecurityService()
    node_service = NodeService(
        node_repo=NodeRepository(),
        graph_repo=GraphRepository(),
        projection_repo=ProjectionRepository(),
        security=security,
    )

    def list(self, request):
        """
        GET /nodes/?graph_id=...
        """
        graph_id = request.query_params.get("graph_id")
        if not graph_id:
            return Response({"detail": "graph_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        # keep it simple for now (repo can later add list_nodes)
        from .models import GNode
        nodes = GNode.objects.filter(graph_id=graph_id).order_by("name")
        # Security: force access check via graph service (cheapest)
        GraphService(graph_repo=GraphRepository(), security=self.security).get_graph(_ctx(request), graph_id)
        return Response(NodeSerializer(nodes, many=True).data)

    def retrieve(self, request, pk=None):
        from .models import GNode
        node = GNode.objects.get(id=pk)
        GraphService(graph_repo=GraphRepository(), security=self.security).get_graph(_ctx(request), node.graph_id)
        return Response(NodeSerializer(node).data)

    def create(self, request):
        s = NodeCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        node = self.node_service.create_node(
            _ctx(request),
            graph_id=s.validated_data["graph_id"],
            name=s.validated_data["name"],
            description=s.validated_data.get("description"),
            is_start=s.validated_data.get("is_start", False),
            ms4_node_id=s.validated_data.get("ms4_node_id"),
        )
        return Response(NodeSerializer(node).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        s = NodeUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)

        node = self.node_service.update_node(
            _ctx(request),
            pk,
            name=s.validated_data.get("name"),
            description=s.validated_data.get("description"),
            is_start=s.validated_data.get("is_start"),
            ms4_node_id=s.validated_data.get("ms4_node_id"),
        )
        return Response(NodeSerializer(node).data)

    def destroy(self, request, pk=None):
        # simple delete with access gate
        self.node_service.delete_node(_ctx(request), pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="attach-ms4")
    def attach_ms4(self, request, pk=None):
        ms4_node_id = request.data.get("ms4_node_id")
        if not ms4_node_id:
            return Response({"detail": "ms4_node_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        node = self.node_service.attach_ms4_node(_ctx(request), pk, ms4_node_id)
        return Response(NodeSerializer(node).data)

    @action(detail=True, methods=["post"], url_path="detach-ms4")
    def detach_ms4(self, request, pk=None):
        node = self.node_service.detach_ms4_node(_ctx(request), pk)
        return Response(NodeSerializer(node).data)


# ----------------------------
# Edge endpoints
# ----------------------------

class EdgeViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    edge_service = EdgeService.build_default()

    def list(self, request):
        graph_id = request.query_params.get("graph_id")
        if not graph_id:
            return Response({"detail": "graph_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        edges = self.edge_service.list_edges(_extract_bearer_token(request), graph_id)
        return Response(EdgeSerializer(edges, many=True).data)

    def retrieve(self, request, pk=None):
        edge = self.edge_service.get_edge(_extract_bearer_token(request), pk)
        return Response(EdgeSerializer(edge).data)

    def create(self, request):
        s = EdgeCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        edge = self.edge_service.create_edge(
            jwt_token=_extract_bearer_token(request),
            graph_id=s.validated_data["graph_id"],
            source_node_id=s.validated_data["source_node_id"],
            dest_node_id=s.validated_data["dest_node_id"],
        )
        return Response(EdgeSerializer(edge).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        self.edge_service.delete_edge(_extract_bearer_token(request), pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ----------------------------
# Rule endpoints
# ----------------------------


def _extract_bearer_token(request) -> str:
    """
    Expect: Authorization: Bearer <jwt>
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return ""
    return auth.split(" ", 1)[1].strip()


class RuleViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Repos (DB access)
        self.rule_repo = RuleRepository()
        self.projection_repo = ProjectionRepository()
        self.prompt_repo = PromptTemplateRepository()

        # Services (business logic)
        self.rule_service = RuleService(
            rule_repo=self.rule_repo,
            projection_repo=self.projection_repo,
            prompt_repo=self.prompt_repo,
            security=SecurityService(),
        )

    def _ctx(self, request) -> RequestContext:
        return RequestContext(jwt_token=_extract_bearer_token(request))

    # -------------------------
    # CRUD
    # -------------------------

    def list(self, request):
        graph_id = request.query_params.get("graph_id")
        if not graph_id:
            raise ValidationError({"detail": "graph_id is required."})

        owner_node_id = request.query_params.get("owner_node_id")

        rules = self.rule_repo.list_rules_for_graph(graph_id=graph_id, owner_node_id=owner_node_id)
        return Response(RuleSerializer(rules, many=True).data)

    def retrieve(self, request, pk=None):
        """
        GET /rules/{id}/
        """
        rule = self.rule_service.get_rule_details(self._ctx(request), pk)
        return Response(RuleSerializer(rule).data, status=status.HTTP_200_OK)

    def create(self, request):
        """
        POST /rules/

        Body (IMPORTANT):
        - input_projection_ids MUST be a list of UUIDs (ordered)
        - output_ffo_ids MUST be a list of UUIDs
        - no template_text in request
        """
        ser = RuleCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        rule = self.rule_service.create_rule_full(
            self._ctx(request),
            graph_id=data["graph_id"],
            owner_node_id=data["owner_node_id"],
            name=data.get("name", ""),
            firing_mode=data.get("firing_mode", "SINGLE"),
            is_terminal=data.get("is_terminal", False),
            input_projection_ids=data["input_projection_ids"],
            output_ffo_ids=data.get("output_ffo_ids", []),
            output_fbo_ids=data.get("output_fbo_ids", []),
            max_iterations=data.get("max_iterations"),
        )

        # Return the created rule (prompt template is created internally)
        rule = self.rule_repo.get_rule_with_details(rule.id)  # good for outputs/prefetch
        return Response(RuleSerializer(rule).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        """
        PATCH /rules/{id}/

        Supports updating scalar fields (name, firing_mode, is_terminal)
        and re-wiring outputs (output_ffo_ids, output_fbo_ids).

        Enforces controller exclusivity:
        - Sending output_ffo_ids clears any existing FBO outputs.
        - Sending output_fbo_ids clears any existing FFO outputs.
        - Setting is_terminal=true clears ALL outputs (terminal = no outputs).
        """
        ser = RuleUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)

        updated = self.rule_service.update_rule_outputs(
            ctx=self._ctx(request),
            rule_id=pk,
            validated=ser.validated_data,
        )
        updated = self.rule_repo.get_rule_with_details(pk)
        return Response(RuleSerializer(updated).data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        """
        DELETE /rules/{id}/
        """
        self.rule_service.delete_rule(self._ctx(request), pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # -------------------------
    # Prompt Template editing
    # -------------------------

    @action(detail=True, methods=["get"], url_path="prompt-template")
    def get_prompt_template(self, request, pk=None):
        """
        GET /rules/{id}/prompt-template/
        """
        ctx = self._ctx(request)

        rule = self.rule_repo.get_rule_with_details(pk)
        SecurityService().assert_project_access(ctx, rule.graph.project_id)

        tpl = self.prompt_repo.get_template(rule_id=pk)
        return Response(PromptTemplateSerializer(tpl).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path="prompt-template")
    def update_prompt_template(self, request, pk=None):
        """
        PATCH /rules/{id}/prompt-template/
        Body: { "template_text": "..." }
        """
        ser = PromptTemplateUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        tpl = self.rule_service.update_prompt_template_text(
            self._ctx(request),
            rule_id=pk,
            template_text=ser.validated_data["template_text"],
        )
        return Response(PromptTemplateSerializer(tpl).data, status=status.HTTP_200_OK)

# ----------------------------
# PromptTemplate endpoints (edit text only)
# ----------------------------

class PromptTemplateViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    prompt_service = PromptTemplateService(
        prompt_repo=PromptTemplateRepository(),
        rule_repo=RuleRepository(),
        security=SecurityService(),
    )

    def retrieve(self, request, pk=None):
        """
        pk here is rule_id (since template is 1:1 with rule)
        """
        tpl = self.prompt_service.get_template(_ctx(request), pk)
        return Response(PromptTemplateSerializer(tpl).data)

    @action(detail=True, methods=["patch"], url_path="text")
    def update_text(self, request, pk=None):
        """
        PATCH /prompt-templates/{rule_id}/text/
        body: { "template_text": "..." }
        """
        s = PromptTemplateUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        tpl = self.prompt_service.update_template_text(
            _ctx(request),
            pk,
            new_text=s.validated_data["template_text"],
        )
        return Response(PromptTemplateSerializer(tpl).data)


# ----------------------------
# Snapshot endpoint (read model)
# ----------------------------

class GraphSnapshotViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    read_service = GraphReadService(security=SecurityService())

    def retrieve(self, request, pk=None):
        """
        GET /graph-snapshots/{graph_id}/
        """
        data = self.read_service.get_graph_snapshot(_ctx(request), pk)
        return Response(data)


# ----------------------------
# Projection endpoints
# ----------------------------

class ProjectionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    security = SecurityService()

    def list(self, request):
        """
        GET /projections/?owner_node=...
        """
        owner_node = request.query_params.get("owner_node") or request.query_params.get("owner_node_id")
        if not owner_node:
            return Response({"detail": "owner_node is required."}, status=400)

        # Security: ensure user has access to the graph this node belongs to
        # (This is a bit indirect, but we can check via Node -> Graph)
        from .models import GNode, Projection
        try:
            node = GNode.objects.get(id=owner_node)
        except GNode.DoesNotExist:
            return Response({"detail": "Node not found."}, status=status.HTTP_404_NOT_FOUND)

        # Authorize
        GraphService(graph_repo=GraphRepository(), security=self.security).get_graph(_ctx(request), node.graph_id)

        projections = Projection.objects.filter(owner_node_id=owner_node)
        return Response(ProjectionSerializer(projections, many=True).data)





class FFOViewSet(viewsets.ViewSet):
    ffo_service = FFOService(FFORepository())

    def list(self, request):
        graph_id = request.query_params.get("graph_id")
        if not graph_id:
            raise ValidationError({"detail": "graph_id is required."})

        owner_node_id = request.query_params.get("owner_node_id")
        dest_node_id = request.query_params.get("dest_node_id")

        rows = self.ffo_service.list_ffos(
            graph_id=graph_id,
            owner_node_id=owner_node_id,
            dest_node_id=dest_node_id,
        )
        return Response(FFOSerializer(rows, many=True).data)


class FFIViewSet(viewsets.ViewSet):
    ffi_service = FFIService(FFIRepository())

    def list(self, request):
        graph_id = request.query_params.get("graph_id")
        if not graph_id:
            raise ValidationError({"detail": "graph_id is required."})

        owner_node_id = request.query_params.get("owner_node_id")
        source_node_id = request.query_params.get("source_node_id")

        rows = self.ffi_service.list_ffis(
            graph_id=graph_id,
            owner_node_id=owner_node_id,
            source_node_id=source_node_id,
        )
        return Response(FFISerializer(rows, many=True).data)


class FBIViewSet(viewsets.ViewSet):
    """
    Read-only listing of Feed-Backward Input buffers.
    These are auto-created when a feedback edge is detected.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        from .models import FBI
        graph_id = request.query_params.get("graph_id")
        if not graph_id:
            raise ValidationError({"detail": "graph_id is required."})
        qs = FBI.objects.filter(graph_id=graph_id).select_related("owner_node", "source_node")
        if request.query_params.get("owner_node_id"):
            qs = qs.filter(owner_node_id=request.query_params["owner_node_id"])
        return Response(FBISerializer(qs, many=True).data)


class FBOViewSet(viewsets.ViewSet):
    """
    Read-only listing of Feed-Backward Output buffers.
    These are auto-created when a feedback edge is detected.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        from .models import FBO
        graph_id = request.query_params.get("graph_id")
        if not graph_id:
            raise ValidationError({"detail": "graph_id is required."})
        qs = FBO.objects.filter(graph_id=graph_id).select_related("owner_node", "dest_node")
        if request.query_params.get("owner_node_id"):
            qs = qs.filter(owner_node_id=request.query_params["owner_node_id"])
        return Response(FBOSerializer(qs, many=True).data)






























from django.views.generic import TemplateView

class GraphControlUITestView(TemplateView):
    template_name = "graphcontrol/ui_test.html"