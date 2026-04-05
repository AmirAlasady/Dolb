from django.db import transaction
from rest_framework.exceptions import ValidationError

from .security import SecurityService, RequestContext
from .exceptions import ResourceNotFound
from ..models import PromptTemplate, Rule, RuleInput, Graph


class PromptTemplateService:
    def __init__(self, prompt_repo=None, rule_repo=None, security: SecurityService | None = None):
        self.prompt_repo = prompt_repo
        self.rule_repo = rule_repo
        self.security = security or SecurityService()

    def _get_rule_or_404(self, rule_id) -> Rule:
        try:
            if self.rule_repo:
                return self.rule_repo.get_rule_with_details(rule_id)
            return Rule.objects.select_related("graph").get(id=rule_id)
        except Rule.DoesNotExist:
            raise ResourceNotFound(f"Rule {rule_id} not found.")

    def _assert_access(self, ctx: RequestContext, rule: Rule):
        graph = rule.graph if hasattr(rule, "graph") else Graph.objects.get(id=rule.graph_id)
        self.security.assert_project_access(ctx, graph.project_id)

    def _build_placeholder_map_from_rule_inputs(self, rule_id) -> dict:
        """
        Deterministic: in1..inN by RuleInput.position
        """
        rows = list(
            RuleInput.objects.filter(rule_id=rule_id).order_by("position").values_list("projection_id", flat=True)
        )
        return {f"in{i+1}": str(pid) for i, pid in enumerate(rows)}

    @transaction.atomic
    def get_template(self, ctx: RequestContext, rule_id) -> PromptTemplate:
        rule = self._get_rule_or_404(rule_id)
        self._assert_access(ctx, rule)

        try:
            return PromptTemplate.objects.get(rule_id=rule_id)
        except PromptTemplate.DoesNotExist:
            raise ResourceNotFound("PromptTemplate not found for this rule.")

    @transaction.atomic
    def create_template_if_missing(self, ctx: RequestContext, rule_id, *, default_text: str) -> PromptTemplate:
        """
        Your rule creation flow should call this once.
        If already exists, do nothing.
        """
        rule = self._get_rule_or_404(rule_id)
        self._assert_access(ctx, rule)

        tpl, created = PromptTemplate.objects.get_or_create(
            rule_id=rule_id,
            defaults={
                "template_text": default_text,
                "placeholder_map": self._build_placeholder_map_from_rule_inputs(rule_id),
            },
        )
        return tpl

    @transaction.atomic
    def update_template_text(self, ctx: RequestContext, rule_id, *, new_text: str) -> PromptTemplate:
        """
        User can edit only the text. We keep placeholder_map controlled by the system.
        """
        if new_text is None or not new_text.strip():
            raise ValidationError("template_text cannot be empty.")

        rule = self._get_rule_or_404(rule_id)
        self._assert_access(ctx, rule)

        tpl = PromptTemplate.objects.get(rule_id=rule_id)
        tpl.template_text = new_text
        tpl.save()
        return tpl

    @transaction.atomic
    def sync_placeholders_to_rule_inputs(self, ctx: RequestContext, rule_id) -> PromptTemplate:
        """
        Call this if rule inputs are edited later.
        It updates placeholder_map to match RuleInput ordering.
        (Does NOT change user template text.)
        """
        rule = self._get_rule_or_404(rule_id)
        self._assert_access(ctx, rule)

        tpl = PromptTemplate.objects.get(rule_id=rule_id)
        tpl.placeholder_map = self._build_placeholder_map_from_rule_inputs(rule_id)
        tpl.save()
        return tpl
