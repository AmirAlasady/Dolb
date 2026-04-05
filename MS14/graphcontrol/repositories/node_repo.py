from django.db import transaction
from ..models import GNode, Projection
from .errors import NodeNotFound


class NodeRepository:
    def create_node(self, graph_id, name, description=None, is_start=False, ms4_node_id=None) -> GNode:
        with transaction.atomic():
            node = GNode.objects.create(
                graph_id=graph_id,
                name=name,
                description=description,
                is_start=is_start,
                ms4_node_id=ms4_node_id
            )

            # Auto-create seed projection for start nodes
            if is_start:
                Projection.objects.get_or_create(
                    graph_id=graph_id,
                    owner_node=node,
                    ffi=None,  # Seed
                    defaults={'created_by_rule': None}
                )

            return node

    def get_node(self, node_id) -> GNode:
        try:
            return GNode.objects.get(id=node_id)
        except GNode.DoesNotExist:
            raise NodeNotFound(f"Node {node_id} not found.")

    def list_nodes(self, graph_id) -> list[GNode]:
        return list(GNode.objects.filter(graph_id=graph_id))

    def update_node(self, node_id, **kwargs) -> GNode:
        node = self.get_node(node_id)

        with transaction.atomic():
            # If disabling is_start: delete seed projection (CASCADE policy allows it)
            if node.is_start and kwargs.get('is_start') is False:
                Projection.objects.filter(owner_node=node, ffi__isnull=True).delete()

            for k, v in kwargs.items():
                setattr(node, k, v)

            node.save()

            # If enabling is_start: ensure seed exists idempotently
            if node.is_start:
                Projection.objects.get_or_create(
                    graph_id=node.graph_id,
                    owner_node=node,
                    ffi=None,
                    defaults={'created_by_rule': None}
                )

            return node
