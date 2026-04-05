from django.db import transaction, IntegrityError as DjangoIntegrityError
from ..models import *
from .base_repo import BaseRepository
from .errors import ProjectionAlreadyUsed, InvalidRuleOutputs, RuleNotFound
from django.db import IntegrityError
from django.db.models import Prefetch
class RuleRepository(BaseRepository):
    def create_rule(self, graph_id, owner_node_id, name, firing_mode, is_terminal, max_iterations=None) -> Rule:
        return Rule.objects.create(
            graph_id=graph_id,
            owner_node_id=owner_node_id,
            name=name,
            firing_mode=firing_mode,
            is_terminal=is_terminal,
            max_iterations=max_iterations,
        )

    def attach_rule_inputs(self, rule, projection_ids_with_position):
        rule_inputs = []
        for pid, pos in projection_ids_with_position:
            rule_inputs.append(RuleInput(
                rule=rule,
                projection_id=pid,
                position=pos
            ))
        
        try:
            RuleInput.objects.bulk_create(rule_inputs)
        except DjangoIntegrityError as e:
            if 'unique_projection_usage' in str(e):
                raise ProjectionAlreadyUsed("One or more projections are already used by another rule.")
            if 'unique_input_position_per_rule' in str(e):
                raise ProjectionAlreadyUsed("Input position conflict within rule.")
            raise e

    def attach_rule_outputs(self, rule, ffo_ids):
        # 1. Terminal Logic Check
        if rule.is_terminal and ffo_ids:
            raise InvalidRuleOutputs("Terminal rules cannot have outputs.")
        if not rule.is_terminal and not ffo_ids:
            raise InvalidRuleOutputs("Non-terminal rules must have at least one output.")

        if not ffo_ids:
            return

        # 2. Graph & Ownership Consistency Check
        valid_ffo_count = FFO.objects.filter(
            id__in=ffo_ids, 
            graph_id=rule.graph_id, 
            owner_node_id=rule.owner_node_id
        ).count()

        if valid_ffo_count != len(ffo_ids):
            raise InvalidRuleOutputs("One or more output buffers do not belong to the rule's owner node or graph.")

        # 3. Attach
        rule.outputs.set(ffo_ids)

    def get_rule_with_details(self, rule_id):
        # We manually construct the query because of prefetch requirements,
        # but we handle the error using the logic matching get_or_throw.
        try:
            return Rule.objects.select_related('prompt_template')\
                               .prefetch_related('ruleinput_set', 'outputs')\
                               .get(id=rule_id)
        except Rule.DoesNotExist:
            raise RuleNotFound(f"Rule {rule_id} not found.")

    def delete_rule(self, rule_id):
        rule = self.get_or_throw(Rule, rule_id, RuleNotFound)
        rule.delete()

    def list_rules_for_graph(self, *, graph_id, owner_node_id=None):
        """
        List rules for a graph (optionally filtered by owner_node).
        Prefetch outputs to avoid N+1.
        """
        qs = Rule.objects.filter(graph_id=graph_id).select_related("owner_node")

        if owner_node_id:
            qs = qs.filter(owner_node_id=owner_node_id)

        return qs.prefetch_related("outputs").order_by("-created_at")

    def get_rule_with_details(self, rule_id) -> Rule:
        """
        Used by RuleService.get_rule_details/delete/update prompt.
        """
        try:
            return (
                Rule.objects.select_related("graph", "owner_node")
                .prefetch_related(
                    "outputs",
                    Prefetch("ruleinput_set", queryset=RuleInput.objects.select_related("projection").order_by("position")),
                )
                .get(id=rule_id)
            )
        except Rule.DoesNotExist:
            raise NotFoundError(f"Rule {rule_id} not found.")

    def get_prompt_template(self, rule_id) -> PromptTemplate:
        try:
            return PromptTemplate.objects.get(rule_id=rule_id)
        except PromptTemplate.DoesNotExist:
            raise NotFoundError(f"Prompt Template for Rule {rule_id} not found.")