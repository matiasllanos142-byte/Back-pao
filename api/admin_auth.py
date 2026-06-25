from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password


ADMIN_COOKIE_NAME = "admin_session"
ADMIN_JWT_ALGORITHM = "HS256"


def _cookie_secure():
    return getattr(settings, "AUTH_COOKIE_SECURE", not settings.DEBUG)


def _cookie_samesite():
    return getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax")


def verify_admin_credentials(username, password):
    expected_username = getattr(settings, "ADMIN_USERNAME", "")
    password_hash = getattr(settings, "ADMIN_PASSWORD_HASH", "")

    if not expected_username or not password_hash:
        return False

    return username == expected_username and check_password(password, password_hash)


def _get_bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def create_admin_token(username):
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=getattr(settings, "ADMIN_TOKEN_TTL", 86400))
    payload = {
        "sub": username,
        "role": "admin",
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.ADMIN_JWT_SECRET, algorithm=ADMIN_JWT_ALGORITHM)


def get_admin_from_request(request):
    token = request.COOKIES.get(ADMIN_COOKIE_NAME) or _get_bearer_token(request)
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.ADMIN_JWT_SECRET,
            algorithms=[ADMIN_JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        return None

    username = payload.get("sub")
    if payload.get("role") != "admin" or username != settings.ADMIN_USERNAME:
        return None

    return {"username": username}


def set_admin_cookie(response, token):
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=getattr(settings, "ADMIN_TOKEN_TTL", 86400),
    )
    return response


def clear_admin_cookie(response):
    response.delete_cookie(ADMIN_COOKIE_NAME, samesite=_cookie_samesite())
    return response
