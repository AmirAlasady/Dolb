# MS2/products/custom_auth.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.models import TokenUser # Import TokenUser
from rest_framework_simplejwt.settings import api_settings as simple_jwt_settings
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.exceptions import InvalidToken

class ForceTokenUserJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        """
        Returns a TokenUser instance based on the validated token.
        Bypasses any local database User lookup for JWT authentication.
        """
        try:
            # simple_jwt_settings.USER_ID_CLAIM refers to what you set in settings.py
            # e.g., "user_id"
            user_id = validated_token[simple_jwt_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken(_("Token contained no recognizable user identification"))

        # Correct way to instantiate TokenUser: pass the validated_token
        # The TokenUser class will internally use USER_ID_CLAIM and USER_ID_FIELD
        # from your SIMPLE_JWT settings to extract the user ID and set its 'id' or 'pk'.
        token_user = TokenUser(validated_token)

        # The TokenUser's 'id' (and 'pk') attribute should now be populated correctly
        # by its own __init__ method based on the validated_token and your SIMPLE_JWT settings
        # for USER_ID_CLAIM and USER_ID_FIELD.

        # Example: If you wanted to verify or access it (not strictly necessary here)
        # print(f"TokenUser ID: {token_user.id}, TokenUser PK: {token_user.pk}")

        return token_user