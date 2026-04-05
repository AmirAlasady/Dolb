from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound


class ServiceLogicError(ValidationError):
    """Use for domain/business rule violations."""
    pass


class AccessDenied(PermissionDenied):
    """Use when user doesn't own/hasn't access to a project/graph."""
    pass


class ResourceNotFound(NotFound):
    """Use when graph/node/rule etc doesn't exist."""
    pass
