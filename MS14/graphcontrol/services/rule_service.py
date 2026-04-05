from __future__ import annotations

from typing import Optional, List, Dict, Tuple

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .security import SecurityService, RequestContext
from .exceptions import ResourceNotFound, ServiceLogicError

from ..models import Graph, GNode, Rule, Projection, FFO, FFI, FBO, FBI
from ..repositories.errors import ProjectionAlreadyUsed, InvalidRuleOutputs


class RuleService:
    def __init__(self, rule_repo, projection_repo, prompt_repo, security: Optional[SecurityService] = None):
        self.rule_repo = rule_repo
        self.projection_repo = projection_repo
        self.prompt_repo = prompt_repo
        self.security = security or SecurityService()

    # --------------------------
    # Helpers
    # --------------------------

    def _get_graph_or_404(self, graph_id) -> Graph:
        try:
            return Graph.objects.get(id=graph_id)
        except Graph.DoesNotExist:
            raise ResourceNotFound(f"Graph {graph_id} not found.")

    def _get_node_or_404(self, node_id) -> GNode:
        try:
            return GNode.objects.get(id=node_id)
        except GNode.DoesNotExist:
            raise ResourceNotFound(f"Node {node_id} not found.")

    def _build_default_template_text(self, input_count: int) -> str:
        """
        Auto-generated template when a rule is created (1:1 with Rule).
        User can edit later.
        """
        lines = ["You are an assistant.", ""]
        for i in range(1, input_count + 1):
            lines += [f"Input {i}:", f"{{in{i}}}", ""]
        lines += ["Task: Process these inputs and return a result."]
        return "\n".join(lines)

    def _build_placeholder_map(self, projection_ids_in_order: List[str]) -> Dict[str, str]:
        """
        {"in1": "<proj_uuid_1>", "in2": "<proj_uuid_2>", ...}
        """
        return {f"in{idx}": str(pid) for idx, pid in enumerate(projection_ids_in_order, start=1)}

    def _create_derived_projections_for_rule_outputs(
        self,
        *,
        rule: Rule,
        input_projection_ids: List[str],
    ) -> None:
        """
        For each forward output FFO (owner -> dest), create a Derived Projection on dest node:
          - owner_node = dest_node
          - ffi = FFI(dest_node <- owner_node)
          - created_by_rule = rule
          - op = rule.firing_mode
          - children = rule input projections
        """
        input_projs = list(Projection.objects.filter(id__in=input_projection_ids))
        if len(input_projs) != len(input_projection_ids):
            raise ValidationError("One or more input projections do not exist (while building derived projections).")

        outputs = list(rule.outputs.all().select_related("dest_node"))

        for out in outputs:
            dest_node_id = out.dest_node_id
            owner_node_id = rule.owner_node_id

            ffi, _ = FFI.objects.get_or_create(
                graph_id=rule.graph_id,
                owner_node_id=dest_node_id,
                source_node_id=owner_node_id,
            )

            derived = Projection.objects.create(
                graph_id=rule.graph_id,
                owner_node_id=dest_node_id,
                ffi=ffi,
                created_by_rule=rule,
                op=rule.firing_mode,
            )
            derived.children.set(input_projs)

    def _create_fbo_derived_projections(
        self,
        *,
        rule: Rule,
        input_projection_ids: List[str],
        output_fbo_ids: List[str],
    ) -> None:
        """
        For each feedback output FBO (controller -> dest), create a Derived Projection
        on the DESTINATION (home-run) node:
          - owner_node = dest_node  (the home-run / start node)
          - fbi = FBI(dest_node <- controller_node)
          - created_by_rule = rule
          - op = rule.firing_mode
          - children = rule input projections

        This projection represents ~Controller[...] and is selectable in subsequent
        rules that run on the destination node in the next loop iteration.
        """
        input_projs = list(Projection.objects.filter(id__in=input_projection_ids))
        if len(input_projs) != len(input_projection_ids):
            raise ValidationError("One or more input projections do not exist (while building FBI derived projections).")

        fbo_outputs = list(FBO.objects.filter(id__in=output_fbo_ids).select_related("dest_node"))

        for fbo in fbo_outputs:
            dest_node_id = fbo.dest_node_id
            controller_node_id = rule.owner_node_id

            # Ensure FBI exists: dest node receives feedback from controller
            fbi, _ = FBI.objects.get_or_create(
                graph_id=rule.graph_id,
                owner_node_id=dest_node_id,
                source_node_id=controller_node_id,
            )

            # Create derived projection: ~Controller[input_contexts...]
            derived = Projection.objects.create(
                graph_id=rule.graph_id,
                owner_node_id=dest_node_id,
                fbi=fbi,
                ffi=None,
                created_by_rule=rule,
                op=rule.firing_mode,
            )
            derived.children.set(input_projs)

    # --------------------------
    # Core
    # --------------------------

    @transaction.atomic
    def create_rule_full(
        self,
        ctx: RequestContext,
        *,
        graph_id,
        owner_node_id,
        name: str = "",
        firing_mode: str = "SINGLE",
        is_terminal: bool = False,
        input_projection_ids: List[str],
        output_ffo_ids: Optional[List[str]] = None,
        output_fbo_ids: Optional[List[str]] = None,
        max_iterations: Optional[int] = None,
    ):
        """
        Creates:
        - Rule
        - RuleInput rows (positions auto from list order)
        - Rule.outputs (FFO) or Rule.fbo_outputs (FBO) M2M
        - PromptTemplate (auto-generated, 1:1)
        - Derived Projections on downstream nodes

        Contracts:
        - input_projection_ids: ["uuid", ...]
        - output_ffo_ids: forward outputs — for non-terminal, non-controller rules
        - output_fbo_ids: feedback outputs — for controller rules sending ~X[...] back upstream
        - A rule may have EITHER FFO outputs OR FBO outputs, NOT both (controller exclusivity).
        - Terminal rules must have no outputs.
        """
        output_ffo_ids = output_ffo_ids or []
        output_fbo_ids = output_fbo_ids or []
        has_ffo = bool(output_ffo_ids)
        has_fbo = bool(output_fbo_ids)

        graph = self._get_graph_or_404(graph_id)
        self.security.assert_project_access(ctx, graph.project_id)

        owner_node = self._get_node_or_404(owner_node_id)
        if owner_node.graph_id != graph_id:
            raise ValidationError("owner_node does not belong to this graph.")

        # --- 1. FIRING MODE VALIDATION ---
        num_inputs = len(input_projection_ids)
        if num_inputs == 0:
            raise ValidationError("Rule must have at least 1 input projection.")
        if num_inputs == 1:
            if firing_mode != "SINGLE":
                raise ValidationError("A rule with exactly 1 input must use firing_mode='SINGLE'.")
        if num_inputs > 1:
            if firing_mode == "SINGLE":
                raise ValidationError(f"A rule with {num_inputs} inputs cannot use SINGLE. Use AND or OR.")
            if firing_mode not in ["AND", "OR"]:
                raise ValidationError("Invalid firing_mode for multiple inputs.")

        if len(set(input_projection_ids)) != len(input_projection_ids):
            raise ValidationError("Duplicate projection in rule inputs is not allowed.")

        # --- 2. TERMINAL / OUTPUT VALIDATION ---
        if is_terminal and (has_ffo or has_fbo):
            raise ValidationError("Terminal rule must not define outputs.")
        if not is_terminal and not has_ffo and not has_fbo:
            raise ValidationError("Non-terminal rule must define at least one output (FFO or FBO).")
        if has_ffo and has_fbo:
            raise ValidationError(
                "Controller exclusivity violation: a rule cannot output to both FFO (forward) "
                "and FBO (feedback) simultaneously. Choose one direction per rule."
            )

        # --- 2b. max_iterations validation ---
        if max_iterations is not None:
            if max_iterations < 1:
                raise ValidationError("max_iterations must be at least 1.")
            if not has_fbo:
                raise ValidationError(
                    "max_iterations can only be set on controller rules (rules with FBO outputs). "
                    "This rule has no FBO outputs."
                )
            if is_terminal:
                raise ValidationError("A terminal rule cannot have max_iterations.")

        # --- 3. INPUT PROJECTION VALIDATION ---
        projections = list(
            Projection.objects.filter(id__in=input_projection_ids).select_related("owner_node")
        )
        if len(projections) != len(input_projection_ids):
            raise ValidationError("One or more input projections do not exist.")

        proj_by_id = {str(p.id): p for p in projections}

        for pid in input_projection_ids:
            p = proj_by_id.get(str(pid))
            if p is None:
                raise ValidationError("One or more input projections do not exist.")
            if p.graph_id != graph_id:
                raise ValidationError("One or more input projections are not in this graph.")
            if p.owner_node_id != owner_node_id:
                raise ValidationError("Rule cannot use a projection owned by a different node.")
            if not p.is_selectable:
                raise ServiceLogicError(
                    "You can only use Seed or Derived projections in rules (raw/base is not selectable)."
                )

        # --- 3b. INPUT CONTEXT FAMILY HOMOGENEITY ---
        # All inputs must be from the SAME context family (all FORWARD or all FEEDBACK).
        # Mixing forward and feedback projections in one rule is semantically undefined.
        context_families = {p.context_family for p in projections}
        if len(context_families) > 1:
            raise ValidationError(
                "Rule inputs must all be from the same context family. "
                "Cannot mix FORWARD (FFI-rooted) and FEEDBACK (FBI-rooted) "
                "projections in a single rule."
            )

        # --- 4. OUTPUT FFO VALIDATION ---
        if has_ffo:
            ffos = list(FFO.objects.filter(id__in=output_ffo_ids))
            if len(ffos) != len(set(output_ffo_ids)):
                raise ValidationError("One or more output FFOs do not exist.")
            for o in ffos:
                if o.graph_id != graph_id:
                    raise ValidationError("One or more output FFOs are not in this graph.")
                if o.owner_node_id != owner_node_id:
                    raise ValidationError("Rule outputs must be owned by the rule's owner node.")

        # --- 4b. OUTPUT FBO VALIDATION ---
        if has_fbo:
            fbos = list(FBO.objects.filter(id__in=output_fbo_ids))
            if len(fbos) != len(set(output_fbo_ids)):
                raise ValidationError("One or more output FBOs do not exist.")
            for o in fbos:
                if o.graph_id != graph_id:
                    raise ValidationError("One or more output FBOs are not in this graph.")
                if o.owner_node_id != owner_node_id:
                    raise ValidationError("FBO outputs must be owned by the rule's owner node (controller).")

        # --- 5. CREATE ENTITIES ---

        # A. Create Rule
        rule = self.rule_repo.create_rule(
            graph_id=graph_id,
            owner_node_id=owner_node_id,
            name=name,
            firing_mode=firing_mode,
            is_terminal=is_terminal,
            max_iterations=max_iterations,
        )

        # B. Attach Inputs
        projection_ids_with_position: List[Tuple[str, int]] = [
            (pid, pos) for pos, pid in enumerate(input_projection_ids, start=1)
        ]
        try:
            self.rule_repo.attach_rule_inputs(rule, projection_ids_with_position)
        except ProjectionAlreadyUsed as e:
            raise ServiceLogicError(str(e))

        # C. Attach Outputs (FFO or FBO)
        if has_ffo:
            try:
                self.rule_repo.attach_rule_outputs(rule, output_ffo_ids)
            except InvalidRuleOutputs as e:
                raise ServiceLogicError(str(e))
        if has_fbo:
            rule.fbo_outputs.set(FBO.objects.filter(id__in=output_fbo_ids))

        # D. Create Prompt Template
        placeholder_map = self._build_placeholder_map(input_projection_ids)
        template_text = self._build_default_template_text(len(input_projection_ids))
        self.prompt_repo.create_template(
            rule_id=rule.id,
            placeholder_map=placeholder_map,
            template_text=template_text,
        )

        # E. Create Derived Projections
        if not is_terminal:
            if has_ffo:
                self._create_derived_projections_for_rule_outputs(
                    rule=rule,
                    input_projection_ids=input_projection_ids,
                )
            if has_fbo:
                self._create_fbo_derived_projections(
                    rule=rule,
                    input_projection_ids=input_projection_ids,
                    output_fbo_ids=output_fbo_ids,
                )

        return rule

    def get_rule_details(self, ctx: RequestContext, rule_id):
        rule = self.rule_repo.get_rule_with_details(rule_id)
        graph = self._get_graph_or_404(rule.graph_id)
        self.security.assert_project_access(ctx, graph.project_id)
        return rule

    @transaction.atomic
    def delete_rule(self, ctx: RequestContext, rule_id):
        rule = self.rule_repo.get_rule_with_details(rule_id)
        graph = self._get_graph_or_404(rule.graph_id)
        self.security.assert_project_access(ctx, graph.project_id)
        self.rule_repo.delete_rule(rule_id)

    @transaction.atomic
    def update_rule_outputs(
        self,
        ctx: RequestContext,
        rule_id,
        validated: dict,
    ):
        """
        Handles PATCH /rules/{id}/ — updates scalar fields and/or re-wires outputs.

        Enforces controller exclusivity on update:
        - Setting output_ffo_ids  automatically clears all existing FBO outputs.
        - Setting output_fbo_ids  automatically clears all existing FFO outputs.
        - Setting is_terminal=True automatically clears BOTH output sets.
        """
        rule = self.rule_repo.get_rule_with_details(rule_id)
        graph = self._get_graph_or_404(rule.graph_id)
        self.security.assert_project_access(ctx, graph.project_id)

        # --- Scalar field updates ---
        dirty_fields = []
        for field in ("name", "firing_mode", "is_terminal", "max_iterations"):
            if field in validated:
                setattr(rule, field, validated[field])
                dirty_fields.append(field)
        if dirty_fields:
            rule.save(update_fields=dirty_fields)

        # --- If rule is now terminal, clear ALL outputs (terminal = no outputs) ---
        # This covers the case: PATCH {"is_terminal": true} without sending output fields.
        if validated.get("is_terminal") is True:
            rule.outputs.clear()
            rule.fbo_outputs.clear()
            return rule

        # --- Output re-wiring with exclusivity enforcement ---
        has_ffo_update = "output_ffo_ids" in validated
        has_fbo_update = "output_fbo_ids" in validated

        if has_ffo_update:
            ffo_ids = validated["output_ffo_ids"]
            rule.outputs.set(
                FFO.objects.filter(
                    id__in=ffo_ids,
                    graph_id=rule.graph_id,
                    owner_node_id=rule.owner_node_id,
                )
            )
            # Exclusivity: setting FFO outputs clears any existing FBO outputs
            rule.fbo_outputs.clear()

        if has_fbo_update:
            fbo_ids = validated["output_fbo_ids"]
            rule.fbo_outputs.set(
                FBO.objects.filter(
                    id__in=fbo_ids,
                    graph_id=rule.graph_id,
                    owner_node_id=rule.owner_node_id,
                )
            )
            # Exclusivity: setting FBO outputs clears any existing FFO outputs
            rule.outputs.clear()

        return rule

    @transaction.atomic
    def update_prompt_template_text(self, ctx: RequestContext, rule_id, template_text: str):
        """
        Client edits ONLY template_text after creation.
        placeholder_map stays as created (based on rule inputs).
        """
        rule = self.rule_repo.get_rule_with_details(rule_id)
        graph = self._get_graph_or_404(rule.graph_id)
        self.security.assert_project_access(ctx, graph.project_id)

        if not template_text or not template_text.strip():
            raise ValidationError("template_text cannot be empty.")

        self.prompt_repo.update_template(rule_id=rule_id, text=template_text.strip())
        return self.prompt_repo.get_template(rule_id)