import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q, UniqueConstraint, Index
from django.utils.translation import gettext_lazy as _
from django.db import transaction

# --- Enums ---

class FiringMode(models.TextChoices):
    SINGLE = 'SINGLE', _('Single Input')
    AND = 'AND', _('Synchronous (Wait for All)')
    OR = 'OR', _('Asynchronous (Fire on Any)')

class GNodeType(models.TextChoices):
    STANDARD = 'STANDARD', _('Standard AI Node')
    # Future: ROUTER, TRIGGER

class EdgeType(models.TextChoices):
    FORWARD  = 'FORWARD',  _('Forward')
    FEEDBACK = 'FEEDBACK', _('Feedback (creates cycle)')

# --- Abstract Base ---

class GraphEntity(models.Model):
    """
    Abstract base class providing UUID and strict validation on save.
    'graph' FK is defined in subclasses to allow custom related_names.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Always run full validation before writing to DB
        self.full_clean()
        super().save(*args, **kwargs)

# --- Core Topology Models ---

class Graph(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_id = models.UUIDField(db_index=True, help_text="Reference to MS2 Project")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class GNode(GraphEntity):
    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name='nodes')
    name = models.CharField(max_length=255)
    node_type = models.CharField(max_length=50, choices=GNodeType.choices, default=GNodeType.STANDARD)
    
    # Logic: If True, this node can have a 'Seed' projection (ffi=None)
    is_start = models.BooleanField(default=False)
    
    ms4_node_id = models.UUIDField(null=True, blank=True)
    description = models.TextField(blank=True, null=True, default="")

    class Meta:
        ordering = ['name']
        unique_together = ('graph', 'name')
        constraints = [
            UniqueConstraint(
                fields=['graph', 'ms4_node_id'], 
                name='unique_ms4_node_per_graph',
                condition=Q(ms4_node_id__isnull=False)
            )
        ]
        indexes = [
            Index(fields=['graph', 'node_type']),
        ]
        
    def clean(self):
        super().clean()
        # If start node => must have ZERO incoming forward edges
        # (Feedback edges are allowed to point back to start nodes — that's a "home run")
        if self.is_start and self.pk:
            if self.incoming_edges.filter(edge_type=EdgeType.FORWARD).exists():
                raise ValidationError("Start nodes cannot have any incoming forward edges.")
        
    def __str__(self):
        return self.name

class Edge(GraphEntity):
    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name='edges')
    source_node = models.ForeignKey(GNode, on_delete=models.CASCADE, related_name='outgoing_edges')
    dest_node = models.ForeignKey(GNode, on_delete=models.CASCADE, related_name='incoming_edges')

    # Automatically set during creation — NEVER set by the user directly.
    edge_type = models.CharField(
        max_length=20,
        choices=EdgeType.choices,
        default=EdgeType.FORWARD,
        help_text="Auto-classified: FORWARD if no cycle, FEEDBACK if closing a cycle."
    )

    class Meta:
        unique_together = ('graph', 'source_node', 'dest_node')
        indexes = [
            Index(fields=['graph', 'source_node']),
            Index(fields=['graph', 'dest_node']),
            Index(fields=['graph', 'edge_type']),
        ]

    def clean(self):
        super().clean()

        if self.source_node.graph_id != self.graph_id or self.dest_node.graph_id != self.graph_id:
            raise ValidationError("Nodes must belong to the same Graph as the Edge.")
        if self.source_node_id == self.dest_node_id:
            raise ValidationError("Self-loops are not allowed in this topology.")

        # Start nodes may NOT receive forward edges (they are "root" producers).
        # However, feedback edges ARE allowed to return to start nodes (the "home run" rule).
        if self.dest_node.is_start and self.edge_type == EdgeType.FORWARD:
            raise ValidationError(
                "Cannot create a forward edge into a start node. "
                "Only feedback (cycle-closing) edges may point to start nodes."
            )

    def __str__(self):
        arrow = "~>" if self.edge_type == EdgeType.FEEDBACK else "->"
        return f"{self.source_node.name} {arrow} {self.dest_node.name}"
    
    def delete(self, *args, **kwargs):
        """
        Custom delete to clean up all wiring ghosts and logic orphans.
        Handles both FORWARD (FFI/FFO/Projection) and FEEDBACK (FBI/FBO/Projection) cleanup.
        """
        from .models import FFI, FFO, FBI, FBO, Projection, Rule
        
        with transaction.atomic():
            if self.edge_type == EdgeType.FORWARD:
                # --- Forward edge cleanup (original logic) ---
                target_ffis = FFI.objects.filter(
                    graph_id=self.graph_id,
                    owner_node_id=self.dest_node_id,
                    source_node_id=self.source_node_id
                )
                related_projs = Projection.objects.filter(ffi__in=target_ffis)
                initial_rules = Rule.objects.filter(inputs__in=related_projs).distinct()
                for r in initial_rules:
                    r.delete()  # Rule.delete is recursive
                target_ffis.delete()
                FFO.objects.filter(
                    graph_id=self.graph_id,
                    owner_node_id=self.source_node_id,
                    dest_node_id=self.dest_node_id
                ).delete()

            else:  # FEEDBACK edge cleanup
                # Find FBI(s) tied to this feedback edge
                target_fbis = FBI.objects.filter(
                    graph_id=self.graph_id,
                    owner_node_id=self.dest_node_id,
                    source_node_id=self.source_node_id
                )
                # Find Projections that use these FBI origins and cascade-delete their rules
                related_projs = Projection.objects.filter(fbi__in=target_fbis)
                initial_rules = Rule.objects.filter(inputs__in=related_projs).distinct()
                for r in initial_rules:
                    r.delete()
                # Kill FBI rows (base FBI projections cascade via FK)
                target_fbis.delete()
                # Kill FBO
                FBO.objects.filter(
                    graph_id=self.graph_id,
                    owner_node_id=self.source_node_id,
                    dest_node_id=self.dest_node_id
                ).delete()

            # Kill the physical edge
            super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        creating = self._state.adding

        # This calls clean() because GraphEntity.save() calls full_clean().
        super().save(*args, **kwargs)

        # Only do wiring when edge is newly created
        if creating:
            from .models import FFI, FFO, FBI, FBO, Projection

            with transaction.atomic():
                if self.edge_type == EdgeType.FORWARD:
                    # --- Forward wiring (original behaviour, unchanged) ---
                    ffi, _ = FFI.objects.get_or_create(
                        graph_id=self.graph_id,
                        owner_node_id=self.dest_node_id,
                        source_node_id=self.source_node_id,
                    )
                    FFO.objects.get_or_create(
                        graph_id=self.graph_id,
                        owner_node_id=self.source_node_id,
                        dest_node_id=self.dest_node_id,
                    )
                    # Base (non-selectable) FFI projection on destination
                    Projection.objects.get_or_create(
                        graph_id=self.graph_id,
                        owner_node_id=self.dest_node_id,
                        ffi_id=ffi.id,
                        created_by_rule=None,
                        defaults={"op": None},
                    )

                else:
                    # --- Feedback wiring (new) ---
                    fbo, _ = FBO.objects.get_or_create(
                        graph_id=self.graph_id,
                        owner_node_id=self.source_node_id,
                        dest_node_id=self.dest_node_id,
                    )
                    fbi, _ = FBI.objects.get_or_create(
                        graph_id=self.graph_id,
                        owner_node_id=self.dest_node_id,
                        source_node_id=self.source_node_id,
                    )
                    # Base (non-selectable) FBI projection on destination
                    # This represents ~source_node[raw] — the feedback stream indicator.
                    Projection.objects.get_or_create(
                        graph_id=self.graph_id,
                        owner_node_id=self.dest_node_id,
                        fbi_id=fbi.id,
                        created_by_rule=None,
                        defaults={"op": None, "ffi": None},
                    )

# --- Wiring Endpoints (Buffers) ---

class FFI(GraphEntity):
    """Feed-Forward Input Buffer (Mailbox)"""
    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name='ffis')
    owner_node = models.ForeignKey(GNode, on_delete=models.CASCADE, related_name='ffis')
    source_node = models.ForeignKey(GNode, on_delete=models.CASCADE, related_name='ffis_as_source')

    class Meta:
        unique_together = ('graph', 'owner_node', 'source_node')
        indexes = [
            Index(fields=['graph', 'owner_node']),
        ]

    def clean(self):
        if self.owner_node.graph_id != self.graph_id or self.source_node.graph_id != self.graph_id:
            raise ValidationError("FFI Nodes must match the Graph ID.")

    def __str__(self):
        return f"FFI: {self.owner_node.name} (from {self.source_node.name})"

class FFO(GraphEntity):
    """Feed-Forward Output Buffer (Outbox)"""
    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name='ffos')
    owner_node = models.ForeignKey(GNode, on_delete=models.CASCADE, related_name='ffos')
    dest_node = models.ForeignKey(GNode, on_delete=models.CASCADE, related_name='ffos_as_dest')

    class Meta:
        unique_together = ('graph', 'owner_node', 'dest_node')
        indexes = [
            Index(fields=['graph', 'owner_node']),
        ]

    def clean(self):
        if self.owner_node.graph_id != self.graph_id or self.dest_node.graph_id != self.graph_id:
            raise ValidationError("FFO Nodes must match the Graph ID.")

    def __str__(self):
        return f"FFO: {self.owner_node.name} (to {self.dest_node.name})"


class FBI(GraphEntity):
    """
    Feed-Backward Input Buffer.
    The 'mailbox' on a destination node that receives feedback from a controller node.
    
    Semantic: owner_node can receive a ~source_node[...] feedback context.
    """
    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name='fbis')
    owner_node = models.ForeignKey(
        GNode, on_delete=models.CASCADE, related_name='fbis',
        help_text="The node that receives feedback (the destination / home-run node)."
    )
    source_node = models.ForeignKey(
        GNode, on_delete=models.CASCADE, related_name='fbis_as_source',
        help_text="The controller node emitting the feedback."
    )

    class Meta:
        unique_together = ('graph', 'owner_node', 'source_node')
        indexes = [
            Index(fields=['graph', 'owner_node']),
        ]

    def clean(self):
        if self.owner_node.graph_id != self.graph_id or self.source_node.graph_id != self.graph_id:
            raise ValidationError("FBI Nodes must match the Graph ID.")
        if self.owner_node_id == self.source_node_id:
            raise ValidationError("FBI source and owner cannot be the same node (no self-feedback yet).")

    def __str__(self):
        return f"FBI: {self.owner_node.name} (feedback from {self.source_node.name})"


class FBO(GraphEntity):
    """
    Feed-Backward Output Buffer.
    The 'outbox' on a controller node for emitting feedback to an upstream node.
    
    Semantic: owner_node (controller) sends ~owner_node[...] to dest_node.
    """
    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name='fbos')
    owner_node = models.ForeignKey(
        GNode, on_delete=models.CASCADE, related_name='fbos',
        help_text="The controller node that emits feedback."
    )
    dest_node = models.ForeignKey(
        GNode, on_delete=models.CASCADE, related_name='fbos_as_dest',
        help_text="The node that receives the feedback."
    )

    class Meta:
        unique_together = ('graph', 'owner_node', 'dest_node')
        indexes = [
            Index(fields=['graph', 'owner_node']),
        ]

    def clean(self):
        if self.owner_node.graph_id != self.graph_id or self.dest_node.graph_id != self.graph_id:
            raise ValidationError("FBO Nodes must match the Graph ID.")
        if self.owner_node_id == self.dest_node_id:
            raise ValidationError("FBO owner and dest cannot be the same node.")

    def __str__(self):
        return f"FBO: {self.owner_node.name} (feedback to {self.dest_node.name})"


# --- Logic & Semantics ---

class Rule(GraphEntity):
    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name='rules')
    owner_node = models.ForeignKey(GNode, on_delete=models.CASCADE, related_name='rules')
    
    name = models.CharField(max_length=255, blank=True)
    firing_mode = models.CharField(max_length=20, choices=FiringMode.choices, default=FiringMode.SINGLE)
    is_terminal = models.BooleanField(default=False)

    # Inputs: Enforced via RuleInput through-model
    inputs = models.ManyToManyField('Projection', through='RuleInput', related_name='used_by_rules')
    
    # Forward outputs (FFO) — send result downstream via forward edges
    outputs = models.ManyToManyField(FFO, related_name='fed_by_rules', blank=True)

    # Feedback outputs (FBO) — send result back upstream via feedback edges (controller role)
    # Uses a through-model (RuleFBOOutput) to enable the unique constraint per pair.
    fbo_outputs = models.ManyToManyField(
        'FBO',
        through='RuleFBOOutput',
        related_name='fed_by_rules',
        blank=True,
        help_text="FBO channels this controller rule writes back to (creates ~X[] feedback context)."
    )

    # Loop control — only meaningful for controller rules (FBO outputs).
    # None  = infinite loop; AI agent decides when to exit via its own logic.
    # N > 0 = MS15 forces exit after N completed loop iterations.
    max_iterations = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Only for controller (FBO) rules. "
            "None = infinite (agent decides exit). "
            "N = MS15 forces loop exit after N completed iterations."
        )
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['graph', 'owner_node']),
        ]

    def clean(self):
        # FK integrity (safe to validate here)
        if self.owner_node_id and self.owner_node.graph_id != self.graph_id:
            raise ValidationError("Rule owner must belong to the same graph.")
            
        # CASE 3: No start node has a terminal rule
        if self.is_terminal and self.owner_node and self.owner_node.is_start:
             raise ValidationError("A Start Node cannot have a Terminal Rule. Start nodes produce seeds; they don't terminate the graph flow.")

        # max_iterations validation
        if self.max_iterations is not None:
            if self.max_iterations < 1:
                raise ValidationError("max_iterations must be at least 1.")
            if self.is_terminal:
                raise ValidationError("A terminal rule cannot have max_iterations — terminal rules do not loop.")

        # --- Additional security/consistency checks requested by user ---
        # All projections used as inputs must belong to this graph and be owned
        # by the same node as the rule.  (RuleInput.clean already enforces the
        # owner-node invariant, but it does not prevent somebody from adding
        # a projection from a different graph through the m2m API.)
        for proj in self.inputs.all():
            if proj.graph_id != self.graph_id:
                raise ValidationError("All input projections must belong to the same graph as the rule.")
            if proj.owner_node_id != self.owner_node_id:
                raise ValidationError("Input projections must be owned by the same node that owns the rule.")

        # Forward-output FFOs must also agree on graph/owner
        for ffo in self.outputs.all():
            if ffo.graph_id != self.graph_id:
                raise ValidationError("FFO outputs must belong to the same graph as the rule.")
            if ffo.owner_node_id != self.owner_node_id:
                raise ValidationError("FFO outputs must be owned by the same node that owns the rule.")

        # Feedback-output FBOs must also agree on graph/owner
        for fbo in self.fbo_outputs.all():
            if fbo.graph_id != self.graph_id:
                raise ValidationError("FBO outputs must belong to the same graph as the rule.")
            if fbo.owner_node_id != self.owner_node_id:
                raise ValidationError("FBO outputs must be owned by the same node that owns the rule.")
    
    def delete(self, *args, **kwargs):
        """
        Recursive deletion: When a rule is deleted, all downstream rules 
        that consume its outputs must also die.
        """
        from .models import Rule
        with transaction.atomic():
            # 1. Find all projections this rule produced
            produced_projs = self.generated_projections.all()
            
            # 2. Find all rules that use these projections as inputs
            downstream_rules = Rule.objects.filter(inputs__in=produced_projs).distinct()
            
            for dr in downstream_rules:
                # RECURSE: dr.delete() will trigger its own downstream cleanup
                dr.delete()
            
            # 3. Finally, delete self
            super().delete(*args, **kwargs)

    def __str__(self):
        return f"Rule {self.name or self.id} in {self.owner_node.name}"


class RuleFBOOutput(models.Model):
    """
    Through-model for Rule.fbo_outputs → FBO.
    Created by migration 0007. Enforces one FBO per Rule (unique_fbo_per_rule constraint).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, related_name='fbo_output_links')
    fbo = models.ForeignKey('FBO', on_delete=models.CASCADE, related_name='rule_links')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('rule', 'fbo'), name='unique_fbo_per_rule')
        ]

    def __str__(self):
        return f"RuleFBOOutput: {self.rule} → FBO({self.fbo_id})"


class Projection(GraphEntity):
    """
    Represents a Selectable Semantic Input context.
    
    Context types:
      - Seed:     ffi=None, fbi=None, owner_node.is_start=True     → "I" (initial input)
      - Forward:  ffi=<FFI>, fbi=None                              → "A[I]", "B[A[I]]", etc.
      - Feedback: ffi=None, fbi=<FBI>                              → "~C[...]" notation
    
    Human-readable labels:
      Forward context:  NodeName[child_contexts...]  e.g. "B[A[I]]"
      Feedback context: ~ControllerName[payload]     e.g. "~C[B[A[I]]]"
    """
    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name='projections')
    owner_node = models.ForeignKey(GNode, on_delete=models.CASCADE, related_name='available_projections')
    
    # Forward origin — nullable for Seed and Feedback projections
    ffi = models.ForeignKey(FFI, on_delete=models.CASCADE, related_name='projections', null=True, blank=True)
    
    # Feedback origin — nullable for Seed and Forward projections
    fbi = models.ForeignKey(FBI, on_delete=models.CASCADE, related_name='projections', null=True, blank=True)

    created_by_rule = models.ForeignKey(
        Rule, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='generated_projections'
    )

    op = models.CharField(max_length=20, choices=FiringMode.choices, null=True, blank=True)
    
    children = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        related_name='parents',
        blank=True
    )

    class Meta:
        indexes = [
            Index(fields=['graph', 'owner_node']),
            Index(fields=['ffi']),
            Index(fields=['fbi']),
        ]
        constraints = [
            # Only one seed per node (ffi=null AND fbi=null)
            UniqueConstraint(
                fields=['owner_node'], 
                condition=Q(ffi__isnull=True, fbi__isnull=True), 
                name='unique_seed_projection_per_node'
            )
        ]

    def clean(self):
        if self.owner_node.graph_id != self.graph_id:
            raise ValidationError("Projection owner must match graph.")

        # Exactly one of ffi or fbi must be set (or both None for Seed)
        if self.ffi and self.fbi:
            raise ValidationError("A Projection cannot have both an FFI and an FBI origin. It must be either forward or feedback context.")

        # Validate FFI-origin projection
        if self.ffi:
            if self.ffi.graph_id != self.graph_id:
                raise ValidationError("FFI must match graph.")
            if self.ffi.owner_node_id != self.owner_node_id:
                raise ValidationError("Projection's FFI owner must match Projection owner_node.")

        # Validate FBI-origin projection
        if self.fbi:
            if self.fbi.graph_id != self.graph_id:
                raise ValidationError("FBI must match graph.")
            if self.fbi.owner_node_id != self.owner_node_id:
                raise ValidationError("Projection's FBI owner must match Projection owner_node.")

        # Seed Logic validation
        if self.ffi is None and self.fbi is None:
            if not self.owner_node.is_start:
                raise ValidationError("Only Start Nodes can have a Projection without an FFI or FBI (The Seed).")
            if self.created_by_rule is not None:
                raise ValidationError("A Seed Projection cannot be created by a Rule.")
        
    @property
    def is_home_run(self) -> bool:
        """
        Returns True if this projection represents a completed feedback loop
        returning to the controller node that initiated it.
        This occurs when the projection is derived, its owner node is N,
        and its ancestry contains an FBI where source_node_id == N.
        """
        if self.created_by_rule_id is None:
            return False
            
        return self._has_fbi_from_node(self.owner_node_id)
        
    def _has_fbi_from_node(self, node_id) -> bool:
        """Recursively checks if the projection descends from an FBI originating from node_id."""
        if self.fbi_id is not None:
            return self.fbi.source_node_id == node_id
            
        for child in self.children.all():
            if child._has_fbi_from_node(node_id):
                return True
                
        return False

    @property
    def is_selectable(self) -> bool:
        """
        A projection is usable in rule inputs only if it is:
        - A Seed projection (ffi=None, fbi=None, is_start=True), or
        - A derived projection created by an upstream rule (forward or feedback loop).
        
        Base incoming projections (raw FFI/FBI streams) are not selectable.
        Home-run projections (feedback loop completed) are not selectable.
        """
        if self.is_home_run:
            return False
            
        is_seed = (self.ffi_id is None and self.fbi_id is None and self.owner_node.is_start)
        is_derived = (self.created_by_rule_id is not None)
        return is_seed or is_derived

    @property
    def context_family(self) -> str:
        """
        Returns 'FEEDBACK' if this projection is rooted in an FBI channel
        OR if any of its ancestor projections were rooted in an FBI channel
        (e.g., A[~C[...]]).
        Returns 'FORWARD' otherwise (including seeds).
        Used for rule-level context-family validation (no mixing).
        """
        if self.fbi_id:
            return 'FEEDBACK'
            
        for child in self.children.all():
            if child.context_family == 'FEEDBACK':
                return 'FEEDBACK'
                
        return 'FORWARD'

    @property
    def display_label(self) -> str:
        """
        Returns the human-readable notation for this projection.
        
        Examples:
          Seed:                     "I"
          Forward base (raw):       "A[raw]"
          Forward derived:          "B[A[I]]"  (built from children labels)
          Feedback base (raw):      "~C[raw]"
          Feedback derived:         "~C[B[A[I]]]"
        
        The ~ prefix signals feedback context to the user.
        """
        # --- Seed ---
        if self.ffi is None and self.fbi is None:
            return "I"

        children_list = list(self.children.all())

        # --- Base projection (no rule, no children) ---
        if not self.created_by_rule and not children_list:
            if self.ffi:
                source_name = self.ffi.source_node.name
                return f"{source_name}[raw]"
            else:  # fbi
                source_name = self.fbi.source_node.name
                return f"~{source_name}[raw]"

        # --- Derived projection (created by a rule) ---
        if children_list:
            op_str = " & " if self.op == FiringMode.AND else " | "
            children_labels = op_str.join(c.display_label for c in children_list)
            inner = f"[{children_labels}]"
        else:
            inner = ""

        if self.ffi:
            source_name = self.ffi.source_node.name
            return f"{source_name}{inner}"
        else:  # fbi — feedback context
            source_name = self.fbi.source_node.name
            return f"~{source_name}{inner}"

    def __str__(self):
        return f"Projection({self.display_label}) on {self.owner_node.name}"

class RuleInput(models.Model):
    """
    Through-model linking Rules to Projections.
    Enforces the 'Single-Use Input' law and Deterministic Ordering.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)
    projection = models.ForeignKey(Projection, on_delete=models.CASCADE)
    
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ['position']
        constraints = [
            # The Golden Rule: A projection can be assigned to AT MOST ONE rule.
            UniqueConstraint(fields=['projection'], name='unique_projection_usage'),
            
            # Ensure a rule doesn't use the same projection twice
            UniqueConstraint(fields=['rule', 'projection'], name='unique_input_per_rule'),
            
            # Ensure ordering is stable
            UniqueConstraint(fields=['rule', 'position'], name='unique_input_position_per_rule')
        ]

    def clean(self):
        if self.rule.graph_id != self.projection.graph_id:
            raise ValidationError("Rule and Projection must belong to the same graph.")
        
        if self.rule.owner_node_id != self.projection.owner_node_id:
            raise ValidationError("Rule cannot use a Projection that belongs to a different node.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class PromptTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.OneToOneField(Rule, on_delete=models.CASCADE, related_name='prompt_template')
    template_text = models.TextField()
    
    # Maps {in1} -> projection_id
    placeholder_map = models.JSONField(default=dict)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Template for {self.rule_id}"