# graphcontrol/repositories/projection_repo.py
from django.db import IntegrityError
from django.db.models import Q
from django.db import transaction

from ..models import Projection, RuleInput
from .base_repo import BaseRepository
from .errors import NotFoundError


class ProjectionRepository(BaseRepository):
    def list_projections(self, *, graph_id, owner_node_id=None, selectable_only=False):
        qs = Projection.objects.filter(graph_id=graph_id)
        if owner_node_id:
            qs = qs.filter(owner_node_id=owner_node_id)

        if selectable_only:
            # selectable = seed OR derived
            qs = qs.filter(Q(ffi__isnull=True, owner_node__is_start=True) | Q(created_by_rule__isnull=False))

        return qs.select_related("owner_node", "ffi", "created_by_rule")

    def get_seed(self, *, graph_id, owner_node_id):
        try:
            return Projection.objects.get(graph_id=graph_id, owner_node_id=owner_node_id, ffi__isnull=True)
        except Projection.DoesNotExist:
            raise NotFoundError(f"Seed projection not found for node {owner_node_id}")

    @transaction.atomic
    def ensure_seed_exists(self, *, graph_id, owner_node_id):
        """
        Creates the Seed projection if missing:
        - ffi=None
        - created_by_rule=None
        """
        try:
            seed, _created = Projection.objects.get_or_create(
                graph_id=graph_id,
                owner_node_id=owner_node_id,
                ffi=None,
                defaults={"created_by_rule": None, "op": None},
            )
            return seed
        except IntegrityError:
            # Unique constraint hit in a race ⇒ just fetch it.
            return Projection.objects.get(graph_id=graph_id, owner_node_id=owner_node_id, ffi__isnull=True)

    @transaction.atomic
    def delete_seed_if_safe(self, *, graph_id, owner_node_id):
        """
        Deletes the seed projection ONLY if it is not used by any rule.
        """
        seeds = Projection.objects.filter(graph_id=graph_id, owner_node_id=owner_node_id, ffi__isnull=True)

        if not seeds.exists():
            return

        seed_ids = list(seeds.values_list("id", flat=True))

        # If seed is used by RuleInput => refuse delete (security + data integrity)
        if RuleInput.objects.filter(projection_id__in=seed_ids).exists():
            raise ValueError("Cannot disable start: seed projection is already used by a rule input.")

        seeds.delete()
