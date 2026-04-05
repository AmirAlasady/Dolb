from typing import Optional
from ..repositories.ffo_repo import FFORepository


class FFOService:
    def __init__(self, ffo_repo: FFORepository):
        self.ffo_repo = ffo_repo

    def list_ffos(
        self,
        *,
        graph_id,
        owner_node_id: Optional[str] = None,
        dest_node_id: Optional[str] = None,
    ):
        return self.ffo_repo.list_ffos(
            graph_id=graph_id,
            owner_node_id=owner_node_id,
            dest_node_id=dest_node_id,
        )
