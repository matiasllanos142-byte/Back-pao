from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.exceptions import AuthenticationFailed


class JWTCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                validated_token = self.get_validated_token(raw_token)
                return (self.get_user(validated_token), validated_token)

        token = request.COOKIES.get("session")
        if token is None:
            return None

        try:
            validated_token = AccessToken(token)
            user = self.get_user(validated_token)
            return (user, validated_token)
        except Exception as exc:
            raise AuthenticationFailed("Token inválido o expirado.") from exc
