from typing import Optional
from ..models import FFO
from .base_repo import BaseRepository


class FFORepository(BaseRepository):
    def list_ffos(
        self,
        *,
        graph_id,
        owner_node_id: Optional[str] = None,
        dest_node_id: Optional[str] = None,
    ) -> list[FFO]:
        qs = FFO.objects.filter(graph_id=graph_id)

        if owner_node_id:
            qs = qs.filter(owner_node_id=owner_node_id)
        if dest_node_id:
            qs = qs.filter(dest_node_id=dest_node_id)

        # deterministic order
        return list(qs.order_by("owner_node__name", "dest_node__name"))
