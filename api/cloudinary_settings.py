import base64
import hashlib

from django.conf import settings

from .models import CloudinarySettings


CLOUDINARY_SETTINGS_ID = "cloudinary"


def _key():
    source = getattr(settings, "CLOUDINARY_SETTINGS_SECRET", "") or settings.SECRET_KEY
    return hashlib.sha256(source.encode("utf-8")).digest()


def _xor_bytes(data):
    key = _key()
    return bytes(value ^ key[index % len(key)] for index, value in enumerate(data))


def encrypt_secret(secret):
    encrypted = _xor_bytes(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_secret(value):
    try:
        encrypted = base64.urlsafe_b64decode(value.encode("ascii"))
        return _xor_bytes(encrypted).decode("utf-8")
    except Exception:
        return ""


def get_saved_cloudinary_settings():
    try:
        return CloudinarySettings.objects.get(id=CLOUDINARY_SETTINGS_ID)
    except CloudinarySettings.DoesNotExist:
        return None


def safe_cloudinary_settings(instance=None):
    instance = instance if instance is not None else get_saved_cloudinary_settings()
    if instance:
        return {
            "configured": True,
            "cloudName": instance.cloud_name,
            "apiKey": instance.api_key,
            "apiSecretSet": bool(instance.api_secret_encrypted),
            "apiSecretPreview": "********" if instance.api_secret_encrypted else "",
        }

    env_configured = all(
        [
            settings.CLOUDINARY_CLOUD_NAME,
            settings.CLOUDINARY_API_KEY,
            settings.CLOUDINARY_API_SECRET,
        ]
    )
    return {
        "configured": env_configured,
        "cloudName": settings.CLOUDINARY_CLOUD_NAME if env_configured else "",
        "apiKey": settings.CLOUDINARY_API_KEY if env_configured else "",
        "apiSecretSet": env_configured,
        "apiSecretPreview": "********" if env_configured else "",
    }


def get_cloudinary_credentials():
    instance = get_saved_cloudinary_settings()
    if instance:
        api_secret = decrypt_secret(instance.api_secret_encrypted)
        if instance.cloud_name and instance.api_key and api_secret:
            return {
                "cloud_name": instance.cloud_name,
                "api_key": instance.api_key,
                "api_secret": api_secret,
            }

    if all(
        [
            settings.CLOUDINARY_CLOUD_NAME,
            settings.CLOUDINARY_API_KEY,
            settings.CLOUDINARY_API_SECRET,
        ]
    ):
        return {
            "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
            "api_key": settings.CLOUDINARY_API_KEY,
            "api_secret": settings.CLOUDINARY_API_SECRET,
        }

    return None


def save_cloudinary_settings(cloud_name, api_key, api_secret=None):
    instance = get_saved_cloudinary_settings()
    encrypted_secret = encrypt_secret(api_secret) if api_secret else None

    if not encrypted_secret and instance:
        encrypted_secret = instance.api_secret_encrypted

    if not encrypted_secret:
        raise ValueError("La API secret de Cloudinary es obligatoria.")

    instance, _ = CloudinarySettings.objects.update_or_create(
        id=CLOUDINARY_SETTINGS_ID,
        defaults={
            "cloud_name": cloud_name,
            "api_key": api_key,
            "api_secret_encrypted": encrypted_secret,
        },
    )
    return instance


def resolve_cloudinary_credentials(payload):
    saved = get_cloudinary_credentials()
    cloud_name = (payload.get("cloudName") or "").strip() or (saved or {}).get("cloud_name", "")
    api_key = (payload.get("apiKey") or "").strip() or (saved or {}).get("api_key", "")
    api_secret = (payload.get("apiSecret") or "").strip() or (saved or {}).get("api_secret", "")

    if not cloud_name or not api_key or not api_secret:
        return None

    return {"cloud_name": cloud_name, "api_key": api_key, "api_secret": api_secret}
