from django.contrib import admin
from .models import (
    Graph, GNode, Edge,
    FFI, FFO, FBI, FBO,
    Rule, Projection, RuleInput, RuleFBOOutput,
    PromptTemplate,
)


# -------------------------
# Inlines
# -------------------------

class EdgeInline(admin.TabularInline):
    model = Edge
    extra = 0
    autocomplete_fields = ("source_node", "dest_node")


class FFIInline(admin.TabularInline):
    model = FFI
    extra = 0
    autocomplete_fields = ("owner_node", "source_node")


class FFOInline(admin.TabularInline):
    model = FFO
    extra = 0
    autocomplete_fields = ("owner_node", "dest_node")


class RuleInputInline(admin.TabularInline):
    """
    Rule.inputs uses through=RuleInput, so this is the right way to edit inputs in admin.
    """
    model = RuleInput
    extra = 0
    autocomplete_fields = ("projection",)
    ordering = ("position",)


class PromptTemplateInline(admin.StackedInline):
    """
    Rule <-> PromptTemplate is 1:1
    """
    model = PromptTemplate
    extra = 0


class ProjectionChildrenInline(admin.TabularInline):
    """
    Projection.children is a self M2M, admin shows it via the implicit through model.
    """
    model = Projection.children.through
    fk_name = "from_projection"
    extra = 0
    autocomplete_fields = ("to_projection",)


class RuleFBOOutputInline(admin.TabularInline):
    """
    Shows FBO outputs (feedback channels) wired to a controller rule.
    """
    model = RuleFBOOutput
    extra = 0
    autocomplete_fields = ("fbo",)
    fields = ("fbo",)


# -------------------------
# Admin registrations
# -------------------------

@admin.register(Graph)
class GraphAdmin(admin.ModelAdmin):
    list_display = ("id", "project_id", "name", "created_at", "updated_at")
    search_fields = ("name", "project_id")
    list_filter = ("created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    inlines = (EdgeInline, FFIInline, FFOInline)


@admin.register(GNode)
class GNodeAdmin(admin.ModelAdmin):
    list_display = ("id", "graph", "name", "node_type", "is_start", "ms4_node_id")
    search_fields = ("name", "ms4_node_id", "graph__name")
    list_filter = ("graph", "node_type", "is_start")
    autocomplete_fields = ("graph",)


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ("id", "graph", "source_node", "dest_node")
    list_filter = ("graph",)
    search_fields = ("source_node__name", "dest_node__name", "graph__name")
    autocomplete_fields = ("graph", "source_node", "dest_node")


@admin.register(FFI)
class FFIAdmin(admin.ModelAdmin):
    list_display = ("id", "graph", "owner_node", "source_node")
    list_filter = ("graph",)
    search_fields = ("owner_node__name", "source_node__name", "graph__name")
    autocomplete_fields = ("graph", "owner_node", "source_node")


@admin.register(FFO)
class FFOAdmin(admin.ModelAdmin):
    list_display = ("id", "graph", "owner_node", "dest_node")
    list_filter = ("graph",)
    search_fields = ("owner_node__name", "dest_node__name", "graph__name")
    autocomplete_fields = ("graph", "owner_node", "dest_node")


@admin.register(FBI)
class FBIAdmin(admin.ModelAdmin):
    list_display = ("id", "graph", "owner_node", "source_node")
    list_filter = ("graph",)
    search_fields = ("owner_node__name", "source_node__name", "graph__name")
    autocomplete_fields = ("graph", "owner_node", "source_node")


@admin.register(FBO)
class FBOAdmin(admin.ModelAdmin):
    list_display = ("id", "graph", "owner_node", "dest_node")
    list_filter = ("graph",)
    search_fields = ("owner_node__name", "dest_node__name", "graph__name")
    autocomplete_fields = ("graph", "owner_node", "dest_node")


@admin.register(Projection)
class ProjectionAdmin(admin.ModelAdmin):
    list_display = ("id", "graph", "owner_node", "ffi", "created_by_rule", "op", "is_selectable")
    list_filter = ("graph", "op")
    search_fields = ("owner_node__name", "graph__name", "created_by_rule__id")
    autocomplete_fields = ("graph", "owner_node", "ffi", "created_by_rule")
    inlines = (ProjectionChildrenInline,)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # pulls related objects to reduce N+1 in admin list
        return qs.select_related("graph", "owner_node", "ffi", "created_by_rule")


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("id", "graph", "owner_node", "name", "firing_mode", "is_terminal", "max_iterations", "created_at")
    list_filter = ("graph", "firing_mode", "is_terminal")
    search_fields = ("name", "owner_node__name", "graph__name")
    autocomplete_fields = ("graph", "owner_node")
    readonly_fields = ("created_at", "updated_at")
    inlines = (RuleInputInline, RuleFBOOutputInline, PromptTemplateInline)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("graph", "owner_node")


@admin.register(RuleFBOOutput)
class RuleFBOOutputAdmin(admin.ModelAdmin):
    list_display = ("id", "rule", "fbo")
    list_filter = ("rule__graph",)
    search_fields = ("rule__name", "rule__owner_node__name", "fbo__id")
    autocomplete_fields = ("rule", "fbo")


@admin.register(RuleInput)
class RuleInputAdmin(admin.ModelAdmin):
    list_display = ("id", "rule", "projection", "position")
    list_filter = ("rule__graph",)
    search_fields = ("rule__id", "projection__id", "rule__owner_node__name")
    autocomplete_fields = ("rule", "projection")
    ordering = ("rule", "position")


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "rule")
    search_fields = ("rule__id", "rule__owner_node__name", "rule__graph__name")
    autocomplete_fields = ("rule",)

    # placeholder_map can be big; keep it editable but visible
    fields = ("rule", "template_text", "placeholder_map")