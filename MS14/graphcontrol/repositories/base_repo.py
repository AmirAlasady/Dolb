from django.db import models
from .errors import NotFoundError

class BaseRepository:
    """
    Common utilities for all repositories.
    """
    def get_or_throw(self, model_class: type[models.Model], pk, exception_cls=NotFoundError, msg=None):
        """
        Helper to fetch an object or raise a specific domain exception.
        """
        try:
            return model_class.objects.get(pk=pk)
        except model_class.DoesNotExist:
            error_message = msg or f"{model_class.__name__} with ID {pk} not found."
            raise exception_cls(error_message)

    def exists(self, model_class: type[models.Model], **kwargs) -> bool:
        return model_class.objects.filter(**kwargs).exists()