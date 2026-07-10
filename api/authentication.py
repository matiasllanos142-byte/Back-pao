from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.exceptions import AuthenticationFailed


PUBLIC_AUTH_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/register",
    "/api/auth/register/verify-code",
    "/api/auth/register/resend-code",
    "/api/auth/verify-email",
    "/api/auth/password-reset/request",
    "/api/auth/password-reset/confirm",
}


class JWTCookieAuthentication(JWTAuthentication):
    def _get_verified_user(self, validated_token):
        user = self.get_user(validated_token)
        if not user.is_active or getattr(user, "disabled_at", None) is not None:
            raise AuthenticationFailed("Cuenta deshabilitada.")
        if getattr(user, "email_verified", True) is False:
            raise AuthenticationFailed("Email no verificado.")

        token_version = validated_token.get("token_version", 0)
        if token_version != getattr(user, "auth_token_version", 0):
            raise AuthenticationFailed("Token invalido o expirado.")
        return user

    def authenticate(self, request):
        if request.path_info.startswith("/api/admin"):
            return None

        path = request.path_info.rstrip("/") or request.path_info
        if path in PUBLIC_AUTH_PATHS:
            return None

        if request.method == "GET" and (
            path == "/api/products" or path.startswith("/api/products/")
        ):
            return None

        if path == "/api/payments/webhook":
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
            raise AuthenticationFailed("Token invalido o expirado.") from exc
