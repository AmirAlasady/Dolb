from typing import Optional
from ..models import FFI
from .base_repo import BaseRepository


class FFIRepository(BaseRepository):
    def list_ffis(
        self,
        *,
        graph_id,
        owner_node_id: Optional[str] = None,
        source_node_id: Optional[str] = None,
    ) -> list[FFI]:
        qs = FFI.objects.filter(graph_id=graph_id)

        if owner_node_id:
            qs = qs.filter(owner_node_id=owner_node_id)
        if source_node_id:
            qs = qs.filter(source_node_id=source_node_id)

        return list(qs.order_by("owner_node__name", "source_node__name"))
