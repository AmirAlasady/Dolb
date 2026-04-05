from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .api_views import (
    UserRegistrationView,
    CustomTokenObtainPairView,
    CurrentUserView,
)

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='user-register'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token-create'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('me/', CurrentUserView.as_view(), name='current-user'),
]