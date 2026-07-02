import base64
import hashlib

from django.conf import settings

from .models import NvidiaSettings


NVIDIA_SETTINGS_ID = "nvidia"


def _key():
    source = getattr(settings, "NVIDIA_SETTINGS_SECRET", "") or settings.SECRET_KEY
    return hashlib.sha256(source.encode("utf-8")).digest()


def _xor_bytes(data):
    key = _key()
    return bytes(value ^ key[index % len(key)] for index, value in enumerate(data))


def encrypt_api_key(api_key):
    encrypted = _xor_bytes(api_key.encode("utf-8"))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_api_key(value):
    try:
        encrypted = base64.urlsafe_b64decode(value.encode("ascii"))
        return _xor_bytes(encrypted).decode("utf-8")
    except Exception:
        return ""


def get_saved_nvidia_settings():
    try:
        return NvidiaSettings.objects.get(id=NVIDIA_SETTINGS_ID)
    except NvidiaSettings.DoesNotExist:
        return None


def default_nvidia_base_url():
    return getattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")


def default_nvidia_model():
    return getattr(settings, "NVIDIA_MODEL", "")


def default_nvidia_image_model():
    return getattr(settings, "NVIDIA_IMAGE_MODEL", "")


def safe_nvidia_settings(instance=None):
    instance = instance if instance is not None else get_saved_nvidia_settings()
    env_api_key = getattr(settings, "NVIDIA_API_KEY", "")

    if instance:
        return {
            "configured": bool(instance.api_key_encrypted or env_api_key),
            "apiKeySet": bool(instance.api_key_encrypted or env_api_key),
            "apiKeyPreview": "********" if instance.api_key_encrypted or env_api_key else "",
            "baseUrl": instance.base_url or default_nvidia_base_url(),
            "model": instance.model or default_nvidia_model(),
            "imageModel": instance.image_model or default_nvidia_image_model(),
            "updatedAt": instance.updated_at,
        }

    return {
        "configured": bool(env_api_key),
        "apiKeySet": bool(env_api_key),
        "apiKeyPreview": "********" if env_api_key else "",
        "baseUrl": default_nvidia_base_url(),
        "model": default_nvidia_model(),
        "imageModel": default_nvidia_image_model(),
        "updatedAt": None,
    }


def get_nvidia_credentials():
    instance = get_saved_nvidia_settings()
    env_api_key = getattr(settings, "NVIDIA_API_KEY", "")

    if instance:
        api_key = decrypt_api_key(instance.api_key_encrypted) if instance.api_key_encrypted else env_api_key
        if api_key:
            return {
                "api_key": api_key,
                "base_url": instance.base_url or default_nvidia_base_url(),
                "model": instance.model or default_nvidia_model(),
                "image_model": instance.image_model or default_nvidia_image_model(),
            }

    if env_api_key:
        return {
            "api_key": env_api_key,
            "base_url": default_nvidia_base_url(),
            "model": default_nvidia_model(),
            "image_model": default_nvidia_image_model(),
        }

    return None


def save_nvidia_settings(base_url, model="", image_model="", api_key=None):
    instance = get_saved_nvidia_settings()
    encrypted_key = encrypt_api_key(api_key) if api_key else None

    if not encrypted_key and instance:
        encrypted_key = instance.api_key_encrypted

    instance, _ = NvidiaSettings.objects.update_or_create(
        id=NVIDIA_SETTINGS_ID,
        defaults={
            "api_key_encrypted": encrypted_key or "",
            "base_url": base_url or default_nvidia_base_url(),
            "model": model,
            "image_model": image_model,
        },
    )
    return instance


def resolve_nvidia_credentials(payload):
    saved = get_nvidia_credentials()
    api_key = (payload.get("apiKey") or "").strip() or (saved or {}).get("api_key", "")
    base_url = (payload.get("baseUrl") or "").strip() or (saved or {}).get("base_url", default_nvidia_base_url())
    model = (payload.get("model") or "").strip() or (saved or {}).get("model", default_nvidia_model())
    image_model = (payload.get("imageModel") or "").strip() or (saved or {}).get(
        "image_model",
        default_nvidia_image_model(),
    )

    if not api_key:
        return None

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "image_model": image_model,
    }
