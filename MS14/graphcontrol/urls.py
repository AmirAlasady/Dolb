from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    GraphViewSet,
    NodeViewSet,
    EdgeViewSet,
    RuleViewSet,
    PromptTemplateViewSet,
    GraphSnapshotViewSet,
    ProjectionViewSet,
    FFOViewSet,
    FFIViewSet,
    FBIViewSet,
    FBOViewSet,
)
from .views import GraphControlUITestView

router = DefaultRouter()
router.register(r"graphs", GraphViewSet, basename="graphs")
router.register(r"nodes", NodeViewSet, basename="nodes")
router.register(r"edges", EdgeViewSet, basename="edges")
router.register(r"rules", RuleViewSet, basename="rules")
router.register(r"prompt-templates", PromptTemplateViewSet, basename="prompt-templates")
router.register(r"graph-snapshots", GraphSnapshotViewSet, basename="graph-snapshots")
router.register(r"projections", ProjectionViewSet, basename="projections")
router.register(r"ffos", FFOViewSet, basename="ffos")
router.register(r"ffis", FFIViewSet, basename="ffis")
router.register(r"fbis", FBIViewSet, basename="fbis")
router.register(r"fbos", FBOViewSet, basename="fbos")

urlpatterns = [
    path("", include(router.urls)),
    path("ui/", GraphControlUITestView.as_view(), name="graphcontrol-ui"),

]
