import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError

from .models import Graph, GNode, Projection, Rule, FFO, FBO


class RuleSecurityTests(TestCase):
    """Tests for the graph/owner-node invariants on Rule relationships."""

    def setUp(self):
        self.g1 = Graph.objects.create(name="g1", project_id=uuid.uuid4())
        self.g2 = Graph.objects.create(name="g2", project_id=uuid.uuid4())

        # two nodes in graph1 (one start so we can create a seed projection)
        self.n1 = GNode.objects.create(graph=self.g1, name="n1", is_start=True)
        self.n1b = GNode.objects.create(graph=self.g1, name="n1b")

        # node in graph2
        self.n2 = GNode.objects.create(graph=self.g2, name="n2", is_start=True)

        # seed projections for each start node
        self.p1 = Projection.objects.create(graph=self.g1, owner_node=self.n1)
        self.p2 = Projection.objects.create(graph=self.g2, owner_node=self.n2)

        # some FFO/FBO objects in graph1
        self.ffo = FFO.objects.create(graph=self.g1, owner_node=self.n1, dest_node=self.n1b)
        self.fbo = FBO.objects.create(graph=self.g1, owner_node=self.n1, dest_node=self.n1b)

        # also cross-graph buffers for negative tests
        self.ffo_other = FFO.objects.create(graph=self.g2, owner_node=self.n2, dest_node=self.n2)
        self.fbo_other = FBO.objects.create(graph=self.g2, owner_node=self.n2, dest_node=self.n2)

    def test_valid_links_are_allowed(self):
        r = Rule.objects.create(graph=self.g1, owner_node=self.n1)
        # adding items from same graph/owner should not raise
        r.inputs.add(self.p1)
        r.outputs.add(self.ffo)
        r.fbo_outputs.add(self.fbo)
        # silence any validation
        r.full_clean()

    def test_input_from_different_graph_rejected(self):
        r = Rule.objects.create(graph=self.g1, owner_node=self.n1)
        with self.assertRaises(ValidationError):
            r.inputs.add(self.p2)

    def test_output_ffo_from_different_graph_rejected(self):
        r = Rule.objects.create(graph=self.g1, owner_node=self.n1)
        with self.assertRaises(ValidationError):
            r.outputs.add(self.ffo_other)

    def test_output_fbo_from_different_graph_rejected(self):
        r = Rule.objects.create(graph=self.g1, owner_node=self.n1)
        with self.assertRaises(ValidationError):
            r.fbo_outputs.add(self.fbo_other)

    def test_owner_mismatch_on_input_rejected(self):
        # projection owned by a different node (n1b) but same graph
        proj = Projection.objects.create(graph=self.g1, owner_node=self.n1b)
        r = Rule.objects.create(graph=self.g1, owner_node=self.n1)
        with self.assertRaises(ValidationError):
            r.inputs.add(proj)

    def test_owner_mismatch_on_ffo_rejected(self):
        ffo_bad = FFO.objects.create(graph=self.g1, owner_node=self.n1b, dest_node=self.n1b)
        r = Rule.objects.create(graph=self.g1, owner_node=self.n1)
        with self.assertRaises(ValidationError):
            r.outputs.add(ffo_bad)

    def test_owner_mismatch_on_fbo_rejected(self):
        fbo_bad = FBO.objects.create(graph=self.g1, owner_node=self.n1b, dest_node=self.n1b)
        r = Rule.objects.create(graph=self.g1, owner_node=self.n1)
        with self.assertRaises(ValidationError):
            r.fbo_outputs.add(fbo_bad)
