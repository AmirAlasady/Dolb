from ..models import Graph, GNode, Edge, FFI, FFO, Projection, Rule
from .base_repo import BaseRepository
from .errors import GraphNotFound

class GraphRepository(BaseRepository):
    def create_graph(self, project_id, name, description=None) -> Graph:
        return Graph.objects.create(
            project_id=project_id,
            name=name,
            description=description
        )

    def get_graph(self, graph_id) -> Graph:
        return self.get_or_throw(Graph, graph_id, GraphNotFound)

    def list_graphs(self, project_id, limit=100, offset=0) -> list[Graph]:
        return list(Graph.objects.filter(project_id=project_id)[offset:offset+limit])

    def delete_graph(self, graph_id):
        # We fetch it first to ensure it exists (throws 404 if not), then delete.
        graph = self.get_or_throw(Graph, graph_id, GraphNotFound)
        graph.delete()

    def get_graph_snapshot(self, graph_id):
        """
        Returns a highly optimized structure of the entire graph definition.
        """
        # Ensure graph exists
        self.get_or_throw(Graph, graph_id, GraphNotFound)

        # 1. Nodes
        nodes = list(GNode.objects.filter(graph_id=graph_id).values('id', 'name', 'node_type', 'is_start', 'ms4_node_id'))
        
        # 2. Edges
        edges = list(Edge.objects.filter(graph_id=graph_id).values('source_node_id', 'dest_node_id'))

        # 3. Buffers
        ffis = list(FFI.objects.filter(graph_id=graph_id).values('id', 'owner_node_id', 'source_node_id'))
        ffos = list(FFO.objects.filter(graph_id=graph_id).values('id', 'owner_node_id', 'dest_node_id'))

        # 4. Projections
        projections = list(Projection.objects.filter(graph_id=graph_id).values(
            'id', 'owner_node_id', 'ffi_id', 'created_by_rule_id', 'op'
        ))

        # 5. Rules & Templates
        rules_qs = Rule.objects.filter(graph_id=graph_id).prefetch_related(
            'ruleinput_set',
            'outputs',
            'prompt_template'
        )
        
        rules_data = []
        for r in rules_qs:
            sorted_inputs = sorted(r.ruleinput_set.all(), key=lambda ri: ri.position)
            
            rules_data.append({
                'id': r.id,
                'owner_node_id': r.owner_node_id,
                'firing_mode': r.firing_mode,
                'is_terminal': r.is_terminal,
                'input_projection_ids': [ri.projection_id for ri in sorted_inputs],
                'output_ffo_ids': [o.id for o in r.outputs.all()],
                'prompt_template': {
                    'text': r.prompt_template.template_text,
                    'map': r.prompt_template.placeholder_map
                } if hasattr(r, 'prompt_template') else None
            })

        return {
            'graph_id': str(graph_id),
            'nodes': nodes,
            'edges': edges,
            'wiring': {'ffis': ffis, 'ffos': ffos},
            'projections': projections,
            'rules': rules_data
        }