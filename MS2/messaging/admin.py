from django.contrib import admin
from .models import Saga, SagaStep
# Register your models here.
admin.site.register(Saga)
admin.site.register(SagaStep)