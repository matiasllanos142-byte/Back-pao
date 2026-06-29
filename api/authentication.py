from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.exceptions import AuthenticationFailed


class JWTCookieAuthentication(JWTAuthentication):
    def _get_verified_user(self, validated_token):
        user = self.get_user(validated_token)
        if getattr(user, "email_verified", True) is False:
            raise AuthenticationFailed("Email no verificado.")
        return user

    def authenticate(self, request):
        if request.path_info.startswith("/api/admin"):
            return None

        if request.path_info == "/api/auth/logout":
            return None

        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                validated_token = self.get_validated_token(raw_token)
                return (self._get_verified_user(validated_token), validated_token)

        token = request.COOKIES.get("session")
        if token is None:
            return None

        try:
            validated_token = AccessToken(token)
            user = self._get_verified_user(validated_token)
            return (user, validated_token)
        except Exception as exc:
            raise AuthenticationFailed("Token inválido o expirado.") from exc
