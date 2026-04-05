class RepositoryError(Exception):
    """Base class for repository exceptions."""
    pass

class NotFoundError(RepositoryError):
    pass

class IntegrityError(RepositoryError):
    pass

# Specific Errors
class GraphNotFound(NotFoundError): pass
class NodeNotFound(NotFoundError): pass
class EdgeNotFound(NotFoundError): pass
class RuleNotFound(NotFoundError): pass

class DependencyError(IntegrityError):
    """Raised when attempting to delete a resource that is still in use."""
    pass

class EdgeAlreadyExists(IntegrityError): pass
class SelfLoopNotAllowed(IntegrityError): pass
class CrossGraphReferenceError(IntegrityError): pass
class ProjectionNotSelectable(IntegrityError): pass
class ProjectionAlreadyUsed(IntegrityError): pass
class InvalidRuleOutputs(IntegrityError): pass