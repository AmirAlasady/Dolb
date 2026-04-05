from django.db import transaction
from rest_framework.exceptions import ValidationError

from .security import SecurityService, RequestContext
from .exceptions import ResourceNotFound, ServiceLogicError
from ..models import Graph, GNode, Projection, RuleInput


class NodeService:
    def __init__(self, node_repo, graph_repo=None, projection_repo=None, security: SecurityService | None = None):
        """
        node_repo: NodeRepository (required)
        graph_repo: optional GraphRepository
        projection_repo: optional ProjectionRepository (not required for seed creation)
        security: SecurityService
        """
        self.node_repo = node_repo
        self.graph_repo = graph_repo
        self.projection_repo = projection_repo
        self.security = security or SecurityService()

    def _get_graph_or_404(self, graph_id) -> Graph:
        try:
            if self.graph_repo:
                return self.graph_repo.get_graph(graph_id)
            return Graph.objects.get(id=graph_id)
        except Graph.DoesNotExist:
            raise ResourceNotFound(f"Graph {graph_id} not found.")

    def _get_node_or_404(self, node_id) -> GNode:
        try:
            return GNode.objects.get(id=node_id)
        except GNode.DoesNotExist:
            raise ResourceNotFound(f"Node {node_id} not found.")

    def _assert_ms4_node_unique_in_graph(self, graph_id, ms4_node_id, exclude_gnode_id=None):
        qs = GNode.objects.filter(graph_id=graph_id, ms4_node_id=ms4_node_id)
        if exclude_gnode_id:
            qs = qs.exclude(id=exclude_gnode_id)
        if qs.exists():
            raise ValidationError("This MS4 node is already linked to another GNode in this graph.")

    # -----------------------------
    # Seed Projection helpers
    # -----------------------------
    def _ensure_seed_projection(self, *, graph_id, owner_node_id):
        """
        Start node must have exactly one seed projection:
        - ffi=None
        - created_by_rule=None
        """
        Projection.objects.get_or_create(
            graph_id=graph_id,
            owner_node_id=owner_node_id,
            ffi=None,
            created_by_rule=None,
            defaults={"op": None},
        )

    def _delete_seed_projection_if_safe(self, *, graph_id, owner_node_id):
        """
        If turning off is_start, delete seed ONLY if not used by any RuleInput.
        """
        seeds = Projection.objects.filter(
            graph_id=graph_id,
            owner_node_id=owner_node_id,
            ffi__isnull=True,
            created_by_rule__isnull=True,
        )

        if not seeds.exists():
            return

        seed_ids = list(seeds.values_list("id", flat=True))

        # If any seed is used by a rule, do NOT delete it.
        if RuleInput.objects.filter(projection_id__in=seed_ids).exists():
            raise ServiceLogicError(
                "Cannot disable is_start: the Seed projection is already used by a rule input."
            )

        seeds.delete()

    # -----------------------------
    # CRUD
    # -----------------------------
    @transaction.atomic
    def create_node(
        self,
        ctx: RequestContext,
        graph_id,
        name,
        description=None,
        is_start=False,
        ms4_node_id=None,
    ) -> GNode:
        graph = self._get_graph_or_404(graph_id)

        # Security: user must own / have access to the MS2 project
        self.security.assert_project_access(ctx, graph.project_id)

        # Validate MS4 node if provided (existence + ownership)
        # Validate MS4 node if provided (existence + ownership + CLAIM)
        if ms4_node_id:
            self.security.verify_ms4_node_owned(ctx, ms4_node_id)
            self._assert_ms4_node_unique_in_graph(graph_id, ms4_node_id)
            # --- NEW: Claim ---
            self.security.node_client.claim_node(ctx.jwt_token, ms4_node_id)

        node = self.node_repo.create_node(
            graph_id=graph_id,
            name=name,
            description=description,  # ✅ keep correct spelling (description)
            is_start=is_start,
            ms4_node_id=ms4_node_id,
        )

        # ✅ Critical: auto-create Seed projection for start nodes
        if is_start:
            self._ensure_seed_projection(graph_id=graph_id, owner_node_id=node.id)

        return node

    @transaction.atomic
    def update_node(
        self,
        ctx: RequestContext,
        node_id,
        *,
        name=None,
        description=None,
        is_start=None,
        ms4_node_id=None,
    ) -> GNode:
        node = self._get_node_or_404(node_id)
        graph = self._get_graph_or_404(node.graph_id)

        self.security.assert_project_access(ctx, graph.project_id)

        # Track start toggle
        was_start = bool(node.is_start)
        will_be_start = was_start if is_start is None else bool(is_start)

        if name is not None:
            node.name = name

        if description is not None:
            node.description = description

        # Handle MS4 node change if provided
        if ms4_node_id is not None:
            if ms4_node_id:
                self.security.verify_ms4_node_owned(ctx, ms4_node_id)
                self._assert_ms4_node_unique_in_graph(node.graph_id, ms4_node_id, exclude_gnode_id=node.id)
                
                # claim new
                self.security.node_client.claim_node(ctx.jwt_token, ms4_node_id)
            
            # unclaim old if different
            if node.ms4_node_id and str(node.ms4_node_id) != str(ms4_node_id):
                 self.security.node_client.unclaim_node(ctx.jwt_token, str(node.ms4_node_id))

            node.ms4_node_id = ms4_node_id

        if is_start is not None:
            node.is_start = will_be_start

        node.save()

        # ✅ Apply seed changes AFTER saving node.is_start
        if (not was_start) and will_be_start:
            self._ensure_seed_projection(graph_id=node.graph_id, owner_node_id=node.id)

        if was_start and (not will_be_start):
            self._delete_seed_projection_if_safe(graph_id=node.graph_id, owner_node_id=node.id)

        return node

    # -----------------------------
    # MS4 Linking
    # -----------------------------
    @transaction.atomic
    def attach_ms4_node(self, ctx: RequestContext, node_id, ms4_node_id) -> GNode:
        node = self._get_node_or_404(node_id)
        graph = self._get_graph_or_404(node.graph_id)

        self.security.assert_project_access(ctx, graph.project_id)
        
        # 1. Check existence/ownership (Existing)
        self.security.verify_ms4_node_owned(ctx, ms4_node_id)

        # 2. Check uniqueness in graph (Existing)
        self._assert_ms4_node_unique_in_graph(node.graph_id, ms4_node_id, exclude_gnode_id=node.id)

        # 3. --- NEW: Claim the node in MS4 ---
        # This calls the MS4 internal endpoint to set is_used_in_graph=True
        self.security.node_client.claim_node(ctx.jwt_token, ms4_node_id)

        # 4. If there was a previous node attached, unclaim it
        if node.ms4_node_id and str(node.ms4_node_id) != str(ms4_node_id):
            self.security.node_client.unclaim_node(ctx.jwt_token, str(node.ms4_node_id))

        node.ms4_node_id = ms4_node_id
        node.save()
        return node

    @transaction.atomic
    def detach_ms4_node(self, ctx: RequestContext, node_id) -> GNode:
        node = self._get_node_or_404(node_id)
        graph = self._get_graph_or_404(node.graph_id)

        self.security.assert_project_access(ctx, graph.project_id)

        # --- NEW: Unclaim the node in MS4 ---
        if node.ms4_node_id:
             self.security.node_client.unclaim_node(ctx.jwt_token, str(node.ms4_node_id))

        node.ms4_node_id = None
        node.save()
        return node

    @transaction.atomic
    def delete_node(self, ctx: RequestContext, node_id):
        node = self._get_node_or_404(node_id)
        graph = self._get_graph_or_404(node.graph_id)

        self.security.assert_project_access(ctx, graph.project_id)

        # Unclaim MS4 node if linked
        if node.ms4_node_id:
            self.security.node_client.unclaim_node(ctx.jwt_token, str(node.ms4_node_id))

        node.delete()