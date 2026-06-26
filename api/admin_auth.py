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


def _clean_setting(value):
    cleaned = str(value or "").strip()
    while len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _admin_username():
    return _clean_setting(getattr(settings, "ADMIN_USERNAME", ""))


def _admin_jwt_secret():
    return _clean_setting(getattr(settings, "ADMIN_JWT_SECRET", ""))


def verify_admin_credentials(username, password):
    expected_username = _admin_username()
    password_hash = _clean_setting(getattr(settings, "ADMIN_PASSWORD_HASH", ""))

    if not expected_username or not password_hash:
        return False

    return username.strip().lower() == expected_username.lower() and check_password(password, password_hash)


def _get_bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def create_admin_token(username):
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=getattr(settings, "ADMIN_TOKEN_TTL", 86400))
    subject = _admin_username() or _clean_setting(username)
    payload = {
        "sub": subject,
        "role": "admin",
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    return jwt.encode(payload, _admin_jwt_secret(), algorithm=ADMIN_JWT_ALGORITHM)


def get_admin_from_request(request):
    token = request.COOKIES.get(ADMIN_COOKIE_NAME) or _get_bearer_token(request)
    if not token:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()

    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            _admin_jwt_secret(),
            algorithms=[ADMIN_JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        return None

    username = payload.get("sub")
    expected_username = _admin_username()
    if (
        payload.get("role") != "admin"
        or not username
        or username.lower() != expected_username.lower()
    ):
        return None

    return {"username": expected_username}


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
