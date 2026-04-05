from dataclasses import dataclass
from graphcontrolinternals.clients import ProjectServiceClient, NodeServiceClient
from .exceptions import AccessDenied


@dataclass(frozen=True)
class RequestContext:
    """
    Minimal request context the service layer needs.
    - jwt_token: pass-through token used to call MS2/MS4 on behalf of user
    - user_id: optional (if you want extra checks later)
    """
    jwt_token: str
    user_id: str | None = None


class SecurityService:
    """
    All cross-service authorization lives here (MS2/MS4).
    Keeps application services clean.
    """

    def __init__(
        self,
        project_client: ProjectServiceClient | None = None,
        node_client: NodeServiceClient | None = None,
    ):
        self.project_client = project_client or ProjectServiceClient()
        self.node_client = node_client or NodeServiceClient()

    def assert_project_access(self, ctx: RequestContext, project_id):
        """
        Uses MS2 internal authorize endpoint.
        Raises DRF PermissionDenied/NotFound based on upstream mapping.
        """
        try:
            self.project_client.check_project_access(ctx.jwt_token, project_id)
        except Exception as e:
            # The client already maps to PermissionDenied/NotFound/ValidationError.
            # If you want a consistent type:
            raise AccessDenied(str(e))

    def verify_ms4_node_owned(self, ctx: RequestContext, ms4_node_id):
        """
        Uses MS4 API to ensure node exists & belongs to user (MS4 should enforce ownership).
        Returns node payload if needed.
        """
        return self.node_client.verify_node_existence(ctx.jwt_token, ms4_node_id)
