from rest_framework import serializers

from .models import (
    Graph, GNode, Edge,
    FFI, FFO, FBI, FBO,
    Rule, RuleInput,
    Projection, PromptTemplate
)


# -----------------------
# Graph
# -----------------------

class GraphCreateSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GraphUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GraphSerializer(serializers.ModelSerializer):
    class Meta:
        model = Graph
        fields = ["id", "project_id", "name", "description", "created_at", "updated_at"]


# -----------------------
# Node
# -----------------------

class NodeCreateSerializer(serializers.Serializer):
    graph_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_start = serializers.BooleanField(default=False)
    ms4_node_id = serializers.UUIDField(required=False, allow_null=True)


class NodeUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_start = serializers.BooleanField(required=False)
    ms4_node_id = serializers.UUIDField(required=False, allow_null=True)


class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GNode
        fields = ["id", "graph", "name", "description", "node_type", "is_start", "ms4_node_id"]


# -----------------------
# Edge
# -----------------------

class EdgeCreateSerializer(serializers.Serializer):
    graph_id = serializers.UUIDField()
    source_node_id = serializers.UUIDField()
    dest_node_id = serializers.UUIDField()


class EdgeSerializer(serializers.ModelSerializer):
    graph_id = serializers.UUIDField()
    source_node_id = serializers.UUIDField()
    dest_node_id = serializers.UUIDField()
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Edge
        fields = ["id", "graph_id", "source_node_id", "dest_node_id", "edge_type"]

    def create(self, validated_data):
        return Edge.objects.create(
            graph_id=validated_data["graph_id"],
            source_node_id=validated_data["source_node_id"],
            dest_node_id=validated_data["dest_node_id"],
        )

# -----------------------
# Rule + Inputs + Outputs
# -----------------------

class RuleInputItemSerializer(serializers.Serializer):
    projection = serializers.UUIDField()
    position = serializers.IntegerField(min_value=1)

class RuleCreateSerializer(serializers.Serializer):
    graph_id = serializers.UUIDField()
    owner_node_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    firing_mode = serializers.ChoiceField(choices=Rule._meta.get_field("firing_mode").choices)
    is_terminal = serializers.BooleanField(default=False)

    input_projection_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )

    # Forward outputs — send result downstream
    output_ffo_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        required=False,
    )

    # Feedback outputs — controller rule sending ~X[...] back upstream
    output_fbo_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        required=False,
    )

    # Loop control — only valid for FBO controller rules
    max_iterations = serializers.IntegerField(
        min_value=1,
        required=False,
        allow_null=True,
        help_text="FBO controller rules only. None=infinite, N=forced exit after N iterations.",
    )

    def validate(self, attrs):
        is_terminal = attrs.get("is_terminal", False)
        has_ffo = bool(attrs.get("output_ffo_ids"))
        has_fbo = bool(attrs.get("output_fbo_ids"))

        if is_terminal and (has_ffo or has_fbo):
            raise serializers.ValidationError("Terminal rule must not define outputs.")
        if not is_terminal and not has_ffo and not has_fbo:
            raise serializers.ValidationError("Non-terminal rule must define at least one output (FFO or FBO).")
        if has_ffo and has_fbo:
            raise serializers.ValidationError(
                "Controller exclusivity: cannot output to both FFO and FBO in the same rule."
            )
        return attrs


class RuleUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    firing_mode = serializers.ChoiceField(
        choices=Rule._meta.get_field("firing_mode").choices,
        required=False
    )
    is_terminal = serializers.BooleanField(required=False)

    input_projection_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        required=False
    )
    # Forward outputs — send result downstream
    output_ffo_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        required=False
    )
    # Feedback outputs — controller rule sending ~X[...] back upstream
    output_fbo_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        required=False
    )

    # Loop control
    max_iterations = serializers.IntegerField(
        min_value=1,
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        is_terminal = attrs.get("is_terminal")
        ffo = attrs.get("output_ffo_ids")
        fbo = attrs.get("output_fbo_ids")
        has_ffo = bool(ffo)
        has_fbo = bool(fbo)

        # Only validate output rules if at least one output field is being changed
        if ffo is not None or fbo is not None:
            if is_terminal is True and (has_ffo or has_fbo):
                raise serializers.ValidationError(
                    "Terminal rule must not define outputs — remove output_ffo_ids and output_fbo_ids."
                )
            if is_terminal is False and not has_ffo and not has_fbo:
                raise serializers.ValidationError(
                    "Non-terminal rule must define at least one output (FFO or FBO)."
                )
            if has_ffo and has_fbo:
                raise serializers.ValidationError(
                    "Controller exclusivity: cannot output to both FFO and FBO in the same rule. "
                    "Choose one direction per rule firing."
                )
        return attrs


class RuleSerializer(serializers.ModelSerializer):
    owner_node_id = serializers.UUIDField(read_only=True)
    graph_id = serializers.UUIDField(read_only=True)

    output_ffo_ids = serializers.SerializerMethodField()
    output_fbo_ids = serializers.SerializerMethodField()
    input_projection_ids = serializers.SerializerMethodField()

    class Meta:
        model = Rule
        fields = [
            "id",
            "graph_id",
            "owner_node_id",
            "name",
            "firing_mode",
            "is_terminal",
            "max_iterations",
            "created_at",
            "updated_at",
            "input_projection_ids",
            "output_ffo_ids",
            "output_fbo_ids",
        ]

    def get_output_ffo_ids(self, obj):
        return [str(x.id) for x in obj.outputs.all()]

    def get_output_fbo_ids(self, obj):
        return [str(x.id) for x in obj.fbo_outputs.all()]

    def get_input_projection_ids(self, obj):
        return [str(x.projection_id) for x in obj.ruleinput_set.all().order_by("position")]

class RuleInputSerializer(serializers.ModelSerializer):
    rule_id = serializers.UUIDField(source="rule_id", read_only=True)
    projection_id = serializers.UUIDField(source="projection_id", read_only=True)

    class Meta:
        model = RuleInput
        fields = ["id", "rule_id", "projection_id", "position"]


# -----------------------
# Buffers (FFI/FFO/FBI/FBO)
# -----------------------

class FFISerializer(serializers.ModelSerializer):
    owner_node_id = serializers.UUIDField(read_only=True)
    source_node_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = FFI
        fields = ["id", "graph", "owner_node_id", "source_node_id"]


class FFOSerializer(serializers.ModelSerializer):
    owner_node_id = serializers.UUIDField(read_only=True)
    dest_node_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = FFO
        fields = ["id", "graph", "owner_node_id", "dest_node_id"]


class FBISerializer(serializers.ModelSerializer):
    """Feed-Backward Input Buffer — represents the ~X[...] feedback channel entry point."""
    owner_node_id = serializers.UUIDField(read_only=True)
    source_node_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = FBI
        fields = ["id", "graph", "owner_node_id", "source_node_id"]


class FBOSerializer(serializers.ModelSerializer):
    """Feed-Backward Output Buffer — the controller's feedback outbox."""
    owner_node_id = serializers.UUIDField(read_only=True)
    dest_node_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = FBO
        fields = ["id", "graph", "owner_node_id", "dest_node_id"]


# -----------------------
# Projection
# -----------------------

class ProjectionSerializer(serializers.ModelSerializer):
    owner_node_id = serializers.UUIDField(read_only=True)
    ffi_id = serializers.UUIDField(allow_null=True, read_only=True)
    fbi_id = serializers.UUIDField(allow_null=True, read_only=True)
    created_by_rule_id = serializers.UUIDField(allow_null=True, read_only=True)

    children_ids = serializers.SerializerMethodField()
    is_selectable = serializers.SerializerMethodField()
    is_home_run = serializers.SerializerMethodField()
    display_label = serializers.SerializerMethodField()
    context_family = serializers.SerializerMethodField()

    class Meta:
        model = Projection
        fields = [
            "id", "graph",
            "owner_node_id", "ffi_id", "fbi_id", "created_by_rule_id",
            "op", "children_ids",
            "is_selectable", "is_home_run", "context_family", "display_label",
        ]

    def get_children_ids(self, obj):
        return [str(c.id) for c in obj.children.all()]

    def get_is_selectable(self, obj):
        return obj.is_selectable

    def get_is_home_run(self, obj):
        return obj.is_home_run

    def get_display_label(self, obj):
        """Human-readable label: 'B[A[I]]' for forward, '~C[B[A[I]]]' for feedback."""
        return obj.display_label

    def get_context_family(self, obj):
        """'FEEDBACK' if rooted in an FBI channel, 'FORWARD' otherwise."""
        return obj.context_family


# -----------------------
# PromptTemplate
# -----------------------

class PromptTemplateUpdateSerializer(serializers.Serializer):
    template_text = serializers.CharField()

    def validate_template_text(self, v):
        if not v.strip():
            raise serializers.ValidationError("template_text cannot be empty.")
        return v


class PromptTemplateSerializer(serializers.ModelSerializer):
    rule_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = PromptTemplate
        fields = ["id", "rule_id", "template_text", "placeholder_map"]


# -----------------------
# Snapshot (for UI)
# -----------------------

class GraphSnapshotSerializer(serializers.Serializer):
    graph = GraphSerializer()
    nodes = NodeSerializer(many=True)
    edges = EdgeSerializer(many=True)
    # Forward buffers
    ffis = FFISerializer(many=True)
    ffos = FFOSerializer(many=True)
    # Feedback buffers
    fbis = FBISerializer(many=True)
    fbos = FBOSerializer(many=True)
    projections = ProjectionSerializer(many=True)
    rules = RuleSerializer(many=True)
    rule_inputs = RuleInputSerializer(many=True)
    prompt_templates = PromptTemplateSerializer(many=True)