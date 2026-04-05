from typing import Optional
from ..repositories.ffi_repo import FFIRepository


class FFIService:
    def __init__(self, ffi_repo: FFIRepository):
        self.ffi_repo = ffi_repo

    def list_ffis(
        self,
        *,
        graph_id,
        owner_node_id: Optional[str] = None,
        source_node_id: Optional[str] = None,
    ):
        return self.ffi_repo.list_ffis(
            graph_id=graph_id,
            owner_node_id=owner_node_id,
            source_node_id=source_node_id,
        )
