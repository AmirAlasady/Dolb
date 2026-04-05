from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from .serializers import (
    UserRegistrationSerializer,
    CurrentUserSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
)
from messaging.models import UserSaga, UserSagaStep
from messaging.event_publisher import event_publisher

User = get_user_model()

class UserRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegistrationSerializer

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Uses our custom serializer to include extra claims in the token.
    """
    serializer_class = CustomTokenObtainPairSerializer

class CurrentUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Retrieve details of the currently authenticated user."""
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        """Update the current user's password."""
        user = request.user
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)

    def delete(self, request):
        """Initiates the user deletion saga for the authenticated user."""
        user = request.user

        if UserSaga.objects.filter(user_id=user.id, status=UserSaga.SagaStatus.IN_PROGRESS).exists():
            return Response({"detail": "Account deletion is already in progress."}, status=status.HTTP_409_CONFLICT)
        
        try:
            with transaction.atomic():
                # 1. Soft-delete the user to disable access immediately
                user.is_active = False
                user.save(update_fields=['is_active'])

                tokens = OutstandingToken.objects.filter(user=user)
                for token in tokens:
                    try:
                        RefreshToken(token.token).blacklist()
                    except Exception as e:
                        # This can happen if a token is malformed, but we should continue.
                        print(f"Warning: Could not blacklist token {token.token}: {e}")

                # 2. Create the saga state tracker
                saga = UserSaga.objects.create(user_id=user.id)
                # Define which services need to confirm cleanup
                services_to_confirm = ['ProjectService', 'AIModelService', 'ToolService'] # Add more as your system grows
                for service_name in services_to_confirm:
                    UserSagaStep.objects.create(saga=saga, service_name=service_name)

                # 3. Publish the event. This is the point of no return for the transaction.
                event_publisher.publish_user_deletion_initiated(user_id=user.id)

        except Exception as e:
            # If event publishing fails, the transaction will be rolled back.
            # The user will remain active, and the saga records won't be created.
            print(f"CRITICAL: Failed to initiate user deletion saga for {user.id}. Error: {e}")
            return Response(
                {"error": "The account deletion process could not be started due to a system error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"message": "Your account deletion request has been received and is being processed."},
            status=status.HTTP_202_ACCEPTED
        )