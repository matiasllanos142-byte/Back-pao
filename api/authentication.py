from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.exceptions import AuthenticationFailed


class JWTCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        token = request.COOKIES.get("session")
        if token is None:
            return None

        try:
            validated_token = AccessToken(token)
            user = self.get_user(validated_token)
            return (user, validated_token)
        except Exception as exc:
            raise AuthenticationFailed("Token inválido o expirado.") from exc
