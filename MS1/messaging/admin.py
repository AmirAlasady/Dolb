from django.contrib import admin

# Register your models here.
from .models import UserSaga, UserSagaStep


admin.site.register(UserSaga)
admin.site.register(UserSagaStep)