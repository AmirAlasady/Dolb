# MS4/nodes/repository.py

from typing import List, Optional
import uuid
from .models import Node, NodeStatus

class NodeRepository:
    """
    Acts as a data access layer for the Node model.
    All direct database interactions for Nodes should be in this class.
    """

    def find_by_id(self, node_id: uuid.UUID) -> Optional[Node]:
        """
        Finds a single Node instance by its primary key.

        Returns:
            The Node instance or None if not found.
        """
        try:
            return Node.objects.get(id=node_id)
        except Node.DoesNotExist:
            return None

    def find_by_project(self, project_id: uuid.UUID) -> List[Node]:
        """
        Finds all Node instances belonging to a specific project.

        Returns:
            A list of Node instances.
        """
        return list(Node.objects.filter(project_id=project_id))

    def create(self, *, project_id: uuid.UUID, owner_id: uuid.UUID, name: str) -> Node:
        """
        Creates and saves a new DRAFT Node instance in the database.
        Configuration is intentionally left empty.
        """
        return Node.objects.create(
            project_id=project_id,
            owner_id=owner_id,
            name=name
            # Status defaults to 'draft' from the model definition
        )

    def update(self, node: Node, name: str, configuration: dict, status: str = None) -> Node:
        # ... (This method is already correct from our previous step)
        node.name = name
        node.configuration = configuration
        update_fields = ['name', 'configuration', 'updated_at']
        if status and status in NodeStatus.values:
            node.status = status
            update_fields.append('status')
        node.save(update_fields=update_fields)
        return node

    def delete(self, node: Node) -> None:
        """
        Deletes a Node instance from the database.
        """
        node.delete()