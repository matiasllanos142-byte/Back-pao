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


def default_workbook_skill():
    return getattr(settings, "NVIDIA_WORKBOOK_SKILL", "")


def default_workbook_plan_model():
    return getattr(settings, "NVIDIA_WORKBOOK_PLAN_MODEL", "") or default_nvidia_model()


def default_workbook_build_model():
    return getattr(settings, "NVIDIA_WORKBOOK_BUILD_MODEL", "") or default_nvidia_model()


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
            "workbookSkill": instance.workbook_skill or default_workbook_skill(),
            "workbookPlanModel": instance.workbook_plan_model or default_workbook_plan_model(),
            "workbookBuildModel": instance.workbook_build_model or default_workbook_build_model(),
            "modelCatalog": safe_nvidia_model_catalog(instance),
            "updatedAt": instance.updated_at,
        }

    return {
        "configured": bool(env_api_key),
        "apiKeySet": bool(env_api_key),
        "apiKeyPreview": "********" if env_api_key else "",
        "baseUrl": default_nvidia_base_url(),
        "model": default_nvidia_model(),
        "imageModel": default_nvidia_image_model(),
        "workbookSkill": default_workbook_skill(),
        "workbookPlanModel": default_workbook_plan_model(),
        "workbookBuildModel": default_workbook_build_model(),
        "modelCatalog": safe_nvidia_model_catalog(None),
        "updatedAt": None,
    }


def safe_nvidia_model_catalog(instance=None):
    instance = instance if instance is not None else get_saved_nvidia_settings()
    if not instance:
        return {
            "authorized": bool(getattr(settings, "NVIDIA_API_KEY", "")),
            "refreshedAt": None,
            "lastError": "",
            "models": [],
            "roles": {},
        }

    catalog = instance.model_catalog if isinstance(instance.model_catalog, dict) else {}
    models = catalog.get("models") if isinstance(catalog.get("models"), list) else []
    return {
        "authorized": bool(instance.api_key_encrypted or getattr(settings, "NVIDIA_API_KEY", "")),
        "refreshedAt": instance.model_catalog_refreshed_at,
        "lastError": instance.model_catalog_last_error,
        "models": models,
        "roles": instance.model_roles if isinstance(instance.model_roles, dict) else {},
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
                "workbook_skill": instance.workbook_skill or default_workbook_skill(),
                "workbook_plan_model": instance.workbook_plan_model or default_workbook_plan_model(),
                "workbook_build_model": instance.workbook_build_model or default_workbook_build_model(),
                "model_roles": instance.model_roles if isinstance(instance.model_roles, dict) else {},
            }

    if env_api_key:
        return {
            "api_key": env_api_key,
            "base_url": default_nvidia_base_url(),
            "model": default_nvidia_model(),
            "image_model": default_nvidia_image_model(),
            "workbook_skill": default_workbook_skill(),
            "workbook_plan_model": default_workbook_plan_model(),
            "workbook_build_model": default_workbook_build_model(),
            "model_roles": {},
        }

    return None


def save_nvidia_settings(
    base_url,
    model="",
    image_model="",
    api_key=None,
    workbook_skill="",
    workbook_plan_model="",
    workbook_build_model="",
):
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
            "workbook_skill": workbook_skill,
            "workbook_plan_model": workbook_plan_model,
            "workbook_build_model": workbook_build_model,
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
    workbook_skill = (payload.get("workbookSkill") or "").strip() or (saved or {}).get(
        "workbook_skill",
        default_workbook_skill(),
    )
    workbook_plan_model = (payload.get("workbookPlanModel") or "").strip() or (saved or {}).get(
        "workbook_plan_model",
        default_workbook_plan_model(),
    )
    workbook_build_model = (payload.get("workbookBuildModel") or "").strip() or (saved or {}).get(
        "workbook_build_model",
        default_workbook_build_model(),
    )

    if not api_key:
        return None

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "image_model": image_model,
        "workbook_skill": workbook_skill,
        "workbook_plan_model": workbook_plan_model,
        "workbook_build_model": workbook_build_model,
    }
