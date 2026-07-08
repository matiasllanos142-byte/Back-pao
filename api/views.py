import os
import json
import hashlib
import time
import base64
import secrets
import logging
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse
from rest_framework import status, generics
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
import requests

logger = logging.getLogger(__name__)

from .models import (
    Category,
    NvidiaSettings,
    Product,
    Order,
    OrderItem,
    PasswordResetRequest,
    PendingRegistration,
    PurchasedProduct,
    WorkbookDraft,
)
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    CategorySerializer,
    ProductSerializer,
    ProductListSerializer,
    PurchasedProductSerializer,
    OrderSerializer,
)
from .permissions import IsAdmin
from .permissions import IsEnvAdmin
from .admin_auth import (
    clear_admin_cookie,
    create_admin_token,
    get_admin_from_request,
    set_admin_cookie,
    verify_admin_credentials,
)
from .email_service import (
    EmailDeliveryError,
    read_email_verification_token,
    send_password_reset_code_email,
    send_purchase_confirmation_email,
    send_registration_code_email,
    send_verification_email,
)
from .cloudinary_settings import (
    get_cloudinary_credentials,
    resolve_cloudinary_credentials,
    safe_cloudinary_settings,
    save_cloudinary_settings,
)
from .nvidia_settings import (
    get_saved_nvidia_settings,
    get_nvidia_credentials,
    resolve_nvidia_credentials,
    safe_nvidia_model_catalog,
    safe_nvidia_settings,
    save_nvidia_settings,
)
from .nvidia_client import build_roles, chat_completion, extract_json_object, list_nvidia_models
from .workbook_generator import build_workbook_plan, infer_workbook_payload_from_chat
from .workbook_pdf import render_workbook_pdf

User = get_user_model()

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 días


def make_auth_token(user):
    return str(AccessToken.for_user(user))


def set_auth_cookie(response, user, token=None):
    token = token or make_auth_token(user)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=COOKIE_MAX_AGE,
    )
    return response


def clear_auth_cookie(response):
    response.delete_cookie(COOKIE_NAME, samesite=settings.AUTH_COOKIE_SAMESITE)
    return response


def make_registration_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def pending_registration_expires_at():
    return timezone.now() + timedelta(seconds=settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS)


def password_reset_expires_at():
    return timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_CODE_TTL_SECONDS)


def format_email_delivery_error(exc):
    message = str(exc) or "No se pudo enviar el codigo de verificacion."
    if "own email address" in message and "verify a domain" in message:
        return (
            "Resend esta en modo prueba: con onboarding@resend.dev solo puede enviar "
            "al email dueño de la cuenta de Resend. Para enviar a otros emails hay que verificar un dominio."
        )
    return message


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"].lower().strip()
    name = serializer.validated_data.get("name") or serializer.validated_data.get("first_name", "")
    password = serializer.validated_data["password"]

    existing_user = User.objects.filter(email=email).first()
    if existing_user:
        if existing_user.email_verified:
            return Response(
                {
                    "error": "Ya existe una cuenta con este email. Recupera tu contrasena para ingresar.",
                    "recoverPassword": True,
                    "email": email,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if existing_user.purchased_products.exists() or existing_user.orders.exists():
            return Response(
                {
                    "error": "Este email tiene una cuenta pendiente con actividad asociada. Contactanos para revisarla."
                },
                status=status.HTTP_409_CONFLICT,
            )
        existing_user.delete()

    code = make_registration_code()
    try:
        send_registration_code_email(name, email, code)
    except EmailDeliveryError as exc:
        PendingRegistration.objects.filter(email=email).delete()
        return Response(
            {
                "error": format_email_delivery_error(exc),
                "emailVerificationSent": False,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    PendingRegistration.objects.update_or_create(
        email=email,
        defaults={
            "name": name,
            "password_hash": make_password(password),
            "verification_code_hash": make_password(code),
            "attempts": 0,
            "expires_at": pending_registration_expires_at(),
        },
    )

    response = Response(
        {
            "email": email,
            "emailVerificationRequired": True,
            "emailVerificationSent": True,
            "expiresInSeconds": settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS,
        },
        status=status.HTTP_202_ACCEPTED,
    )
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_registration_code_view(request):
    email = request.data.get("email", "").lower().strip()
    code = request.data.get("code", "").strip()

    if not email or not code:
        return Response({"error": "Email y codigo son obligatorios."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        pending = PendingRegistration.objects.get(email=email)
    except PendingRegistration.DoesNotExist:
        return Response({"error": "No hay una verificacion pendiente para este email."}, status=status.HTTP_400_BAD_REQUEST)

    if pending.is_expired():
        pending.delete()
        return Response({"error": "El codigo vencio. Pedi uno nuevo para continuar."}, status=status.HTTP_400_BAD_REQUEST)

    max_attempts = settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS
    if pending.attempts >= max_attempts:
        pending.delete()
        return Response({"error": "Se supero el limite de intentos. Pedi un nuevo codigo."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    if not check_password(code, pending.verification_code_hash):
        pending.attempts += 1
        pending.save(update_fields=["attempts", "updated_at"])
        remaining = max(max_attempts - pending.attempts, 0)
        return Response(
            {
                "error": "Codigo incorrecto.",
                "attemptsRemaining": remaining,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(email=email).exists():
        pending.delete()
        return Response({"error": "Ya existe una cuenta con este email."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        user = User.objects.create(
            username=email,
            email=email,
            first_name=pending.name,
            is_admin=False,
            password=pending.password_hash,
            email_verified=True,
            email_verified_at=timezone.now(),
        )
        pending.delete()

    token = make_auth_token(user)
    response = Response(
        {"user": UserSerializer(user).data, "accessToken": token},
        status=status.HTTP_201_CREATED,
    )
    return set_auth_cookie(response, user, token)


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_registration_code_view(request):
    email = request.data.get("email", "").lower().strip()
    if not email:
        return Response({"error": "El email es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email=email).exists():
        return Response({"error": "Ya existe una cuenta con este email."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        pending = PendingRegistration.objects.get(email=email)
    except PendingRegistration.DoesNotExist:
        return Response({"error": "No hay una verificacion pendiente para este email."}, status=status.HTTP_400_BAD_REQUEST)

    if pending.is_expired():
        pending.delete()
        return Response({"error": "El codigo vencio. Comenza el registro nuevamente."}, status=status.HTTP_400_BAD_REQUEST)

    code = make_registration_code()
    try:
        send_registration_code_email(pending.name, pending.email, code)
    except EmailDeliveryError as exc:
        return Response(
            {
                "error": format_email_delivery_error(exc),
                "emailVerificationSent": False,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    pending.verification_code_hash = make_password(code)
    pending.expires_at = pending_registration_expires_at()
    pending.attempts = 0
    pending.save(update_fields=["verification_code_hash", "expires_at", "attempts", "updated_at"])

    return Response(
        {
            "email": email,
            "emailVerificationRequired": True,
            "emailVerificationSent": True,
            "expiresInSeconds": settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_request_view(request):
    email = request.data.get("email", "").lower().strip()
    if not email:
        return Response({"error": "El email es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email=email, email_verified=True, is_active=True).first()
    if not user:
        return Response(
            {
                "ok": True,
                "email": email,
                "emailSent": False,
                "message": "Si el email existe, te mandamos un codigo para recuperar la contrasena.",
            }
        )

    code = make_registration_code()
    try:
        send_password_reset_code_email(user.first_name, user.email, code)
    except EmailDeliveryError as exc:
        return Response(
            {
                "error": format_email_delivery_error(exc),
                "emailSent": False,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    PasswordResetRequest.objects.create(
        user=user,
        email=user.email,
        verification_code_hash=make_password(code),
        attempts=0,
        expires_at=password_reset_expires_at(),
    )

    return Response(
        {
            "ok": True,
            "email": user.email,
            "emailSent": True,
            "expiresInSeconds": settings.PASSWORD_RESET_CODE_TTL_SECONDS,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm_view(request):
    email = request.data.get("email", "").lower().strip()
    code = request.data.get("code", "").strip()
    password = request.data.get("password", "")

    if not email or not code or not password:
        return Response(
            {"error": "Email, codigo y contrasena son obligatorios."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(password) < 6:
        return Response(
            {"error": "La contrasena debe tener al menos 6 caracteres."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        reset_request = (
            PasswordResetRequest.objects.select_related("user")
            .filter(email=email, used_at__isnull=True)
            .latest("created_at")
        )
    except PasswordResetRequest.DoesNotExist:
        return Response(
            {"error": "No hay una recuperacion pendiente para este email."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if reset_request.is_expired():
        reset_request.used_at = timezone.now()
        reset_request.save(update_fields=["used_at", "updated_at"])
        return Response(
            {"error": "El codigo vencio. Pedi uno nuevo para continuar."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    max_attempts = settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS
    if reset_request.attempts >= max_attempts:
        reset_request.used_at = timezone.now()
        reset_request.save(update_fields=["used_at", "updated_at"])
        return Response(
            {"error": "Se supero el limite de intentos. Pedi un nuevo codigo."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if not check_password(code, reset_request.verification_code_hash):
        reset_request.attempts += 1
        reset_request.save(update_fields=["attempts", "updated_at"])
        remaining = max(max_attempts - reset_request.attempts, 0)
        return Response(
            {
                "error": "Codigo incorrecto.",
                "attemptsRemaining": remaining,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = reset_request.user
    with transaction.atomic():
        user.set_password(password)
        user.email_verified = True
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()
        user.save(update_fields=["password", "email_verified", "email_verified_at", "updated_at"])

        now = timezone.now()
        PasswordResetRequest.objects.filter(
            user=user,
            used_at__isnull=True,
        ).update(used_at=now, updated_at=now)

    response = Response({"ok": True})
    return clear_auth_cookie(response)


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email_view(request):
    token = request.query_params.get("token", "")
    try:
        payload = read_email_verification_token(token)
        user = User.objects.get(id=payload["user_id"], email=payload["email"])
    except (signing.BadSignature, signing.SignatureExpired, KeyError, User.DoesNotExist):
        if settings.EMAIL_VERIFICATION_ERROR_URL:
            return redirect(settings.EMAIL_VERIFICATION_ERROR_URL)
        return HttpResponse(
            "El enlace de verificacion no es valido o ya expiro.",
            status=400,
            content_type="text/plain; charset=utf-8",
        )

    if not user.email_verified:
        user.mark_email_verified()

    if settings.EMAIL_VERIFICATION_SUCCESS_URL:
        return redirect(settings.EMAIL_VERIFICATION_SUCCESS_URL)

    return HttpResponse(
        "Email verificado correctamente. Ya podes volver a Paola Psicope.",
        content_type="text/plain; charset=utf-8",
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_verification_email_view(request):
    if request.user.email_verified:
        return Response({"ok": True, "emailVerificationSent": False, "alreadyVerified": True})

    try:
        email_result = send_verification_email(request.user, request)
    except EmailDeliveryError:
        return Response({"error": "No se pudo enviar el email de verificacion."}, status=status.HTTP_502_BAD_GATEWAY)

    if not email_result["sent"]:
        return Response(
            {
                "ok": False,
                "emailVerificationSent": False,
                "error": "El envio de emails no esta configurado en el backend.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"ok": True, "emailVerificationSent": email_result["sent"]})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get("email", "").lower().strip()
    password = request.data.get("password", "")

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "Email o contraseña incorrectos."}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.check_password(password):
        return Response({"error": "Email o contraseña incorrectos."}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.email_verified:
        response = Response(
            {
                "error": "Este email todavia no esta verificado. Volve a registrarte para recibir un codigo nuevo."
            },
            status=status.HTTP_403_FORBIDDEN,
        )
        return clear_auth_cookie(response)

    token = make_auth_token(user)
    response = Response({"user": UserSerializer(user).data, "accessToken": token})
    return set_auth_cookie(response, user, token)


@api_view(["POST"])
def logout_view(request):
    response = Response({"ok": True})
    return clear_auth_cookie(response)


@api_view(["GET"])
def me_view(request):
    if request.user.is_authenticated:
        return Response({"user": UserSerializer(request.user).data})
    return Response({"user": None})


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_login_view(request):
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "")

    if not verify_admin_credentials(username, password):
        return Response(
            {"error": "Credenciales de administracion incorrectas."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_admin_token(username)
    response = Response(
        {
            "admin": {"username": username},
            "adminToken": token,
            "token": token,
            "accessToken": token,
        }
    )
    return set_admin_cookie(response, token)


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_logout_view(request):
    response = Response({"ok": True})
    return clear_admin_cookie(response)


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_me_view(request):
    admin = get_admin_from_request(request)
    return Response({"admin": admin})


def sign_cloudinary_upload(params, api_secret):
    payload = "&".join(
        f"{key}={value}"
        for key, value in sorted(params.items())
        if value not in [None, ""]
    )
    return hashlib.sha1(f"{payload}{api_secret}".encode("utf-8")).hexdigest()


def cloudinary_error(response, fallback):
    try:
        data = response.json()
    except ValueError:
        return fallback

    try:
        error = data.get("error")
        if isinstance(error, dict):
            return error.get("message") or fallback
        if isinstance(error, str):
            return error

        message = data.get("message")
        if isinstance(message, str):
            return message

        return fallback
    except Exception:
        return fallback


@api_view(["GET", "PUT"])
@permission_classes([IsEnvAdmin])
def admin_cloudinary_settings_view(request):
    if request.method == "GET":
        return Response({"cloudinary": safe_cloudinary_settings()})

    cloud_name = request.data.get("cloudName", "").strip()
    api_key = request.data.get("apiKey", "").strip()
    api_secret = request.data.get("apiSecret", "").strip()

    if not cloud_name or not api_key:
        return Response(
            {"error": "Cloud name y API key son obligatorios."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        instance = save_cloudinary_settings(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret or None,
        )
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"cloudinary": safe_cloudinary_settings(instance)})


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_cloudinary_settings_test_view(request):
    credentials = resolve_cloudinary_credentials(request.data)
    if not credentials:
        return Response(
            {"error": "Completa las credenciales de Cloudinary."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    auth = base64.b64encode(
        f"{credentials['api_key']}:{credentials['api_secret']}".encode("utf-8")
    ).decode("ascii")
    usage_url = f"https://api.cloudinary.com/v1_1/{credentials['cloud_name']}/usage"

    try:
        response = requests.get(
            usage_url,
            headers={"Authorization": f"Basic {auth}"},
            timeout=20,
        )
    except requests.RequestException:
        return Response(
            {"error": "No se pudo validar Cloudinary."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if response.status_code >= 400:
        return Response(
            {"error": cloudinary_error(response, "Cloudinary rechazo las credenciales.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({"ok": True})


def nvidia_error(response, fallback):
    try:
        data = response.json()
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                return error.get("message") or fallback
            if isinstance(error, str):
                return error
            return data.get("message") or fallback
        return fallback
    except ValueError:
        return fallback


@api_view(["GET", "PUT"])
@permission_classes([IsEnvAdmin])
def admin_nvidia_settings_view(request):
    if request.method == "GET":
        return Response({"nvidia": safe_nvidia_settings()})

    base_url = request.data.get("baseUrl", "").strip()
    model = request.data.get("model", "").strip()
    image_model = request.data.get("imageModel", "").strip()
    workbook_skill = request.data.get("workbookSkill", "").strip()
    workbook_plan_model = request.data.get("workbookPlanModel", "").strip()
    workbook_build_model = request.data.get("workbookBuildModel", "").strip()
    api_key = request.data.get("apiKey", "").strip()

    if not base_url:
        return Response(
            {"error": "La URL base de NVIDIA es obligatoria."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    instance = save_nvidia_settings(
        base_url=base_url,
        model=model,
        image_model=image_model,
        api_key=api_key or None,
        workbook_skill=workbook_skill,
        workbook_plan_model=workbook_plan_model,
        workbook_build_model=workbook_build_model,
    )
    return Response({"nvidia": safe_nvidia_settings(instance)})


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_nvidia_settings_test_view(request):
    credentials = resolve_nvidia_credentials(request.data)
    if not credentials:
        return Response(
            {"error": "Completa la API key de NVIDIA."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    models_url = f"{credentials['base_url'].rstrip('/')}/models"
    try:
        response = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {credentials['api_key']}"},
            timeout=20,
        )
    except requests.RequestException:
        return Response(
            {"error": "No se pudo validar NVIDIA."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if response.status_code >= 400:
        return Response(
            {"error": nvidia_error(response, "NVIDIA rechazo las credenciales.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        data = response.json()
    except ValueError:
        data = {}
    models = data.get("data") if isinstance(data, dict) else []
    return Response({"ok": True, "modelCount": len(models) if isinstance(models, list) else 0})


def _get_or_create_nvidia_settings_for_catalog(credentials):
    instance = get_saved_nvidia_settings()
    if instance:
        return instance
    instance = NvidiaSettings.objects.create(
        id="nvidia",
        base_url=credentials.get("base_url") or "https://integrate.api.nvidia.com/v1",
        model=credentials.get("model", ""),
        image_model=credentials.get("image_model", ""),
        workbook_skill=credentials.get("workbook_skill", ""),
        workbook_plan_model=credentials.get("workbook_plan_model", ""),
        workbook_build_model=credentials.get("workbook_build_model", ""),
    )
    return instance


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_nvidia_models_view(request):
    return Response({"catalog": safe_nvidia_model_catalog()})


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_nvidia_models_refresh_view(request):
    credentials = resolve_nvidia_credentials(request.data)
    if not credentials:
        return Response(
            {"error": "Completa y guarda la API key de NVIDIA antes de refrescar modelos."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    instance = _get_or_create_nvidia_settings_for_catalog(credentials)
    try:
        models = list_nvidia_models(credentials["base_url"], credentials["api_key"])
    except requests.HTTPError as exc:
        response = exc.response
        instance.model_catalog_last_error = nvidia_error(response, "NVIDIA rechazo la consulta de modelos.") if response else str(exc)
        instance.save(update_fields=["model_catalog_last_error", "updated_at"])
        return Response({"error": instance.model_catalog_last_error}, status=status.HTTP_400_BAD_REQUEST)
    except requests.RequestException:
        instance.model_catalog_last_error = "No se pudo consultar el catalogo de modelos NVIDIA."
        instance.save(update_fields=["model_catalog_last_error", "updated_at"])
        return Response({"error": instance.model_catalog_last_error}, status=status.HTTP_502_BAD_GATEWAY)

    roles = build_roles(models, instance.model_roles if isinstance(instance.model_roles, dict) else {})
    instance.model_catalog = {"models": models}
    instance.model_roles = roles
    instance.model_catalog_refreshed_at = timezone.now()
    instance.model_catalog_last_error = ""
    if not instance.model and roles.get("orchestrator"):
        instance.model = roles["orchestrator"]
    if not instance.workbook_plan_model and roles.get("planner"):
        instance.workbook_plan_model = roles["planner"]
    if not instance.workbook_build_model and roles.get("builder"):
        instance.workbook_build_model = roles["builder"]
    if not instance.image_model and roles.get("image"):
        instance.image_model = roles["image"]
    instance.save(
        update_fields=[
            "model_catalog",
            "model_roles",
            "model_catalog_refreshed_at",
            "model_catalog_last_error",
            "model",
            "workbook_plan_model",
            "workbook_build_model",
            "image_model",
            "updated_at",
        ]
    )
    return Response({"catalog": safe_nvidia_model_catalog(instance), "nvidia": safe_nvidia_settings(instance)})


@api_view(["PUT"])
@permission_classes([IsEnvAdmin])
def admin_nvidia_orchestrator_view(request):
    instance = get_saved_nvidia_settings()
    if not instance:
        return Response(
            {"error": "Configura NVIDIA antes de elegir modelos."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    roles = instance.model_roles if isinstance(instance.model_roles, dict) else {}
    for key in ["orchestrator", "planner", "builder", "vision", "image", "code"]:
        value = str(request.data.get(key, "") or "").strip()
        if value:
            roles[key] = value

    instance.model_roles = roles
    instance.model = roles.get("orchestrator", instance.model)
    instance.workbook_plan_model = roles.get("planner", instance.workbook_plan_model)
    instance.workbook_build_model = roles.get("builder", instance.workbook_build_model)
    instance.image_model = roles.get("image", instance.image_model)
    instance.save(
        update_fields=[
            "model_roles",
            "model",
            "workbook_plan_model",
            "workbook_build_model",
            "image_model",
            "updated_at",
        ]
    )
    return Response({"catalog": safe_nvidia_model_catalog(instance), "nvidia": safe_nvidia_settings(instance)})


def safe_workbook_draft(instance):
    plan = instance.plan or {}
    return {
        "id": str(instance.id),
        "title": instance.title,
        "brief": instance.brief,
        "topic": instance.topic,
        "age": instance.age,
        "difficulty": instance.difficulty,
        "pages": instance.pages,
        "style": instance.style,
        "provider": instance.provider,
        "status": instance.status,
        "phase": plan.get("phase") or ("done" if instance.status == "done" else "planning"),
        "plan": plan,
        "pdfReady": instance.status == "done",
        "pdfUrl": f"/api/admin/workbooks/{instance.id}/pdf" if plan else "",
        "warnings": plan.get("warnings", []),
        "agentTrace": plan.get("agentTrace", []),
        "createdAt": instance.created_at,
        "updatedAt": instance.updated_at,
    }


@api_view(["GET", "POST"])
@permission_classes([IsEnvAdmin])
def admin_workbook_list_create_view(request):
    if request.method == "GET":
        drafts = WorkbookDraft.objects.all()[:20]
        return Response({"workbooks": [safe_workbook_draft(draft) for draft in drafts]})

    plan = build_workbook_plan(request.data)
    draft = WorkbookDraft.objects.create(
        title=plan["title"],
        brief=plan["brief"],
        topic=plan["topic"],
        age=plan["age"],
        difficulty=plan["difficulty"],
        pages=plan["requestedPages"],
        style=plan["style"],
        provider="local-dataset",
        status="planned",
        plan=plan,
    )
    return Response({"workbook": safe_workbook_draft(draft)}, status=status.HTTP_201_CREATED)


def _workbook_messages_text(messages):
    lines = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role", "user")
        content = str(message.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _selected_nvidia_model(credentials, role, model_profile="auto"):
    if model_profile and model_profile != "auto":
        return model_profile
    roles = credentials.get("model_roles") if isinstance(credentials.get("model_roles"), dict) else {}
    if role == "planner":
        return roles.get("planner") or credentials.get("workbook_plan_model") or roles.get("orchestrator") or credentials.get("model")
    if role == "builder":
        return roles.get("builder") or credentials.get("workbook_build_model") or roles.get("orchestrator") or credentials.get("model")
    return roles.get("orchestrator") or credentials.get("model")


def _try_nvidia_workbook_plan(messages, credentials, model_profile="auto"):
    model = _selected_nvidia_model(credentials, "planner", model_profile)
    if not credentials or not model:
        return None, "NVIDIA no tiene un modelo de plan configurado."

    skill = credentials.get("workbook_skill", "")
    system_prompt = (
        "Sos el agente planificador de Paola Psicope. Devolve solo JSON valido, sin markdown. "
        "El JSON debe tener: title, brief, topic, age, difficulty, pages, style. "
        "Si faltan datos, inferi una opcion profesional y practica. pages debe ser numero entre 8 y 140."
    )
    user_prompt = (
        f"Skill fija:\n{skill}\n\nConversacion:\n{_workbook_messages_text(messages)}\n\n"
        "Arma el payload base para un cuadernillo psicopedagogico imprimible A4."
    )

    try:
        content = chat_completion(
            credentials["base_url"],
            credentials["api_key"],
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.15,
            max_tokens=1600,
        )
    except Exception as exc:
        return None, f"NVIDIA fallo en planificacion: {exc}"

    payload = extract_json_object(content)
    if not isinstance(payload, dict):
        return None, "NVIDIA no devolvio JSON valido para el plan."

    payload["skill"] = skill
    return payload, ""


def _try_nvidia_build_notes(plan, credentials, model_profile="auto"):
    model = _selected_nvidia_model(credentials, "builder", model_profile)
    if not credentials or not model:
        return None, "NVIDIA no tiene un modelo de build configurado."

    system_prompt = (
        "Sos el agente builder de Paola Psicope. Devolve solo JSON valido, sin markdown. "
        "El JSON debe tener buildNotes: array de textos cortos, y visualDirection: texto breve. "
        "No reescribas actividades completas; solo mejora guia editorial y direccion visual."
    )
    user_prompt = json.dumps(
        {
            "title": plan.get("title"),
            "topic": plan.get("topic"),
            "age": plan.get("age"),
            "difficulty": plan.get("difficulty"),
            "pages": plan.get("totalPages"),
            "style": plan.get("style"),
            "activities": plan.get("activities", [])[:12],
        },
        ensure_ascii=False,
    )

    try:
        content = chat_completion(
            credentials["base_url"],
            credentials["api_key"],
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1300,
        )
    except Exception as exc:
        return None, f"NVIDIA fallo en build: {exc}"

    payload = extract_json_object(content)
    if not isinstance(payload, dict):
        return None, "NVIDIA no devolvio JSON valido para build."
    return payload, ""


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_workbook_chat_view(request):
    messages = request.data.get("messages") or []
    mode = str(request.data.get("mode") or "plan").lower()
    workbook_id = request.data.get("workbookId")
    model_profile = str(request.data.get("modelProfile") or "auto").strip() or "auto"
    if not isinstance(messages, list) or not messages:
        return Response(
            {"error": "Envia al menos un mensaje para armar el plan."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    credentials = get_nvidia_credentials() or {}
    skill_text = credentials.get("workbook_skill", "")
    warnings = []
    agent_trace = []

    if mode == "build" and workbook_id:
        draft = get_object_or_404(WorkbookDraft, pk=workbook_id)
        draft.status = "done"
        draft.plan = {
            **(draft.plan or {}),
            "phase": "done",
            "pdfGeneratedAt": timezone.now().isoformat(),
            "agentTrace": [
                *((draft.plan or {}).get("agentTrace", [])),
                {"agent": "builder", "status": "done", "model": "local-pdf"},
            ],
        }
        draft.save(update_fields=["status", "plan", "updated_at"])
        return Response(
            {
                "reply": "Build terminado. El PDF A4 quedo listo para descargar.",
                "phase": "done",
                "pdfReady": True,
                "warnings": [],
                "agentTrace": draft.plan.get("agentTrace", []),
                "workbook": safe_workbook_draft(draft),
            }
        )

    payload = None
    if credentials:
        payload, nvidia_warning = _try_nvidia_workbook_plan(messages, credentials, model_profile)
        if payload:
            agent_trace.append(
                {
                    "agent": "planner",
                    "status": "ok",
                    "model": _selected_nvidia_model(credentials, "planner", model_profile),
                }
            )
        elif nvidia_warning:
            warnings.append(nvidia_warning)

    if not payload:
        payload = infer_workbook_payload_from_chat(messages, skill_text=skill_text)
        agent_trace.append({"agent": "planner", "status": "fallback", "model": "local-dataset"})

    plan = build_workbook_plan(payload)
    plan = {
        **plan,
        "phase": "planning",
        "warnings": warnings,
        "agentTrace": agent_trace,
    }
    draft = WorkbookDraft.objects.create(
        title=plan["title"],
        brief=plan["brief"],
        topic=plan["topic"],
        age=plan["age"],
        difficulty=plan["difficulty"],
        pages=plan["requestedPages"],
        style=plan["style"],
        provider="nvidia-orchestrator" if credentials and not any(item.get("status") == "fallback" for item in agent_trace) else "local-dataset",
        status="planned",
        plan=plan,
    )
    reply = (
        f"Arme un plan de {plan['totalPages']} hojas A4 para {plan['topic']}. "
        f"Incluye {len(plan['activities'])} actividades, estructura imprimible, registro y certificado. "
        "Revisalo y cuando este bien toca Generar PDF."
    )
    return Response(
        {
            "reply": reply,
            "skill": {
                "name": "Paola Cuadernillos",
                "planModel": credentials.get("workbook_plan_model", ""),
                "buildModel": credentials.get("workbook_build_model", ""),
            },
            "phase": "planning",
            "pdfReady": False,
            "warnings": warnings,
            "agentTrace": agent_trace,
            "workbook": safe_workbook_draft(draft),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_workbook_build_view(request, pk):
    draft = get_object_or_404(WorkbookDraft, pk=pk)
    if not draft.plan:
        return Response(
            {"error": "El cuadernillo no tiene plan para generar."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    credentials = get_nvidia_credentials() or {}
    model_profile = str(request.data.get("modelProfile") or "auto").strip() or "auto"
    warnings = list((draft.plan or {}).get("warnings", []))
    agent_trace = list((draft.plan or {}).get("agentTrace", []))
    build_payload = None
    if credentials:
        build_payload, nvidia_warning = _try_nvidia_build_notes(draft.plan, credentials, model_profile)
        if build_payload:
            agent_trace.append(
                {
                    "agent": "builder",
                    "status": "ok",
                    "model": _selected_nvidia_model(credentials, "builder", model_profile),
                }
            )
        elif nvidia_warning:
            warnings.append(nvidia_warning)
            agent_trace.append({"agent": "builder", "status": "fallback", "model": "local-pdf"})
    else:
        agent_trace.append({"agent": "builder", "status": "fallback", "model": "local-pdf"})

    draft.status = "done"
    draft.plan = {
        **draft.plan,
        "phase": "done",
        "warnings": warnings,
        "agentTrace": agent_trace,
        "buildNotes": (build_payload or {}).get("buildNotes", []),
        "visualDirection": (build_payload or {}).get("visualDirection", ""),
        "pdfGeneratedAt": timezone.now().isoformat(),
    }
    draft.save(update_fields=["status", "plan", "updated_at"])
    return Response(
        {
            "workbook": safe_workbook_draft(draft),
            "phase": "done",
            "pdfReady": True,
            "warnings": warnings,
            "agentTrace": agent_trace,
        }
    )


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_workbook_pdf_view(request, pk):
    draft = get_object_or_404(WorkbookDraft, pk=pk)
    if not draft.plan:
        return Response(
            {"error": "El cuadernillo no tiene plan para descargar."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    pdf_bytes = render_workbook_pdf(draft.plan)
    filename = f"paola-psicope-cuadernillo-{str(draft.id)[:8]}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def grant_order_access(order):
    if not order.user_id or order.status != "completada":
        return

    for item in order.items.select_related("product"):
        PurchasedProduct.objects.update_or_create(
            user=order.user,
            product=item.product,
            defaults={
                "order": order,
                "is_active": True,
            },
        )

    send_purchase_confirmation_email_once(order)


def send_purchase_confirmation_email_once(order):
    if order.purchase_email_sent_at:
        return

    try:
        result = send_purchase_confirmation_email(order)
    except EmailDeliveryError as exc:
        logger.warning("Purchase confirmation email failed for order %s: %s", order.id, exc)
        return

    if not result.get("sent"):
        logger.warning(
            "Purchase confirmation email was not sent for order %s: %s",
            order.id,
            result.get("reason") or "unknown_reason",
        )
        return

    order.purchase_email_sent_at = timezone.now()
    order.save(update_fields=["purchase_email_sent_at", "updated_at"])


def get_backend_public_url(request):
    return (settings.BACKEND_PUBLIC_URL or request.build_absolute_uri("/")).rstrip("/")


def get_payment_notification_url(request):
    return f"{get_backend_public_url(request)}/api/payments/webhook?source_news=webhooks"


def normalize_frontend_url(value):
    raw_value = str(value or "http://localhost:3000")
    candidates = []
    for part in raw_value.replace("\n", ",").replace(";", ",").split(","):
        cleaned = part.strip().strip('"').strip("'").rstrip("/")
        if not cleaned:
            continue
        parsed = urlparse(cleaned)
        if not (parsed.scheme and parsed.netloc):
            if cleaned.startswith(("localhost", "127.0.0.1", "[::1]")):
                cleaned = f"http://{cleaned}"
            else:
                cleaned = f"https://{cleaned}"
        candidates.append(cleaned.rstrip("/"))

    if not candidates:
        return "http://localhost:3000"

    custom_domain = [
        candidate
        for candidate in candidates
        if "up.railway.app" not in urlparse(candidate).netloc
    ]
    return custom_domain[0] if custom_domain else candidates[0]


def get_mercado_pago_sdk():
    import mercadopago

    return mercadopago.SDK(settings.MP_ACCESS_TOKEN)


def get_mercado_pago_mode():
    configured_mode = str(getattr(settings, "MP_MODE", "auto") or "auto").lower().strip()
    if configured_mode in {"test", "sandbox"}:
        return "test"
    if configured_mode in {"production", "prod"}:
        return "production"

    token = str(settings.MP_ACCESS_TOKEN or "").strip()
    return "test" if token.startswith("TEST-") else "production"


def get_mercado_pago_checkout_url(response_body, mode):
    if not isinstance(response_body, dict):
        return ""

    if mode == "test":
        return response_body.get("sandbox_init_point") or response_body.get("init_point") or ""

    return response_body.get("init_point") or ""


def mercado_pago_error_message(response_body, fallback="Mercado Pago rechazo la operacion."):
    if isinstance(response_body, dict):
        raw_message = response_body.get("message") or response_body.get("error") or fallback
        cause_details = mercado_pago_cause_details(response_body)
        if "UNAUTHORIZED" in str(raw_message).upper():
            return (
                "Mercado Pago rechazo la credencial configurada. "
                "Revisa que MP_ACCESS_TOKEN sea el Access Token de produccion "
                "de la cuenta vendedora y que la aplicacion este habilitada."
            )
        if cause_details:
            return f"{raw_message} ({'; '.join(cause_details[:3])})"
        return raw_message
    return fallback


def mercado_pago_cause_details(response_body):
    causes = response_body.get("cause") if isinstance(response_body, dict) else None
    if not isinstance(causes, list):
        return []

    details = []
    for cause in causes:
        if isinstance(cause, dict):
            code = cause.get("code") or cause.get("error_code") or ""
            description = cause.get("description") or cause.get("message") or ""
            detail = " - ".join(str(part) for part in [code, description] if part)
            if detail:
                details.append(detail)
        elif cause:
            details.append(str(cause))
    return details


def is_mercado_pago_back_urls_error(response_body):
    if isinstance(response_body, (dict, list)):
        raw = json.dumps(response_body, ensure_ascii=False)
    else:
        raw = str(response_body or "")
    normalized = raw.lower()
    return "back_urls" in normalized or "back url" in normalized or "back_url" in normalized


def mercado_pago_response_status(status_code, response_body):
    if not isinstance(response_body, dict):
        return status.HTTP_502_BAD_GATEWAY
    raw_message = f"{response_body.get('message', '')} {response_body.get('error', '')}".upper()
    if status_code == 401 or "UNAUTHORIZED" in raw_message:
        return status.HTTP_401_UNAUTHORIZED
    if status_code == 403 or "FORBIDDEN" in raw_message:
        return status.HTTP_403_FORBIDDEN
    if 400 <= status_code < 500:
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_502_BAD_GATEWAY


def validate_mercado_pago_webhook_signature(request, payment_id):
    if not settings.MP_WEBHOOK_SECRET:
        return True

    from mercadopago.webhook import InvalidWebhookSignatureError, WebhookSignatureValidator

    data_id = (
        request.query_params.get("data.id")
        or request.query_params.get("id")
        or str(payment_id)
    )

    try:
        WebhookSignatureValidator.validate(
            request.headers.get("x-signature"),
            request.headers.get("x-request-id"),
            data_id,
            settings.MP_WEBHOOK_SECRET,
        )
        return True
    except InvalidWebhookSignatureError:
        return False


def get_mercado_pago_payment(payment_id):
    result = get_mercado_pago_sdk().payment().get(str(payment_id))
    response_body = result.get("response", {})
    status_code = int(result.get("status") or 500)
    if status_code >= 400:
        return None, mercado_pago_error_message(
            response_body,
            "No se pudo consultar el pago en Mercado Pago.",
        )
    return response_body, ""


def extract_mercado_pago_payment_id(request):
    body = request.data if isinstance(request.data, dict) else {}
    body_data = body.get("data") if isinstance(body.get("data"), dict) else {}
    return (
        body_data.get("id")
        or request.query_params.get("data.id")
        or request.query_params.get("id")
    )


def update_order_from_mercado_pago_payment(payment):
    external_reference = str(payment.get("external_reference") or "").strip()
    if not external_reference:
        metadata = payment.get("metadata") or {}
        external_reference = str(metadata.get("order_id") or "").strip()
    if not external_reference:
        return None

    try:
        order = Order.objects.get(id=external_reference)
    except (Order.DoesNotExist, ValueError):
        return None

    payment_status = str(payment.get("status") or "").lower()
    if payment_status == "approved":
        order.status = "completada"
    elif payment_status in {"rejected", "cancelled"}:
        order.status = "fallida"
    elif payment_status in {"refunded", "charged_back"}:
        order.status = "reembolsada"
    else:
        order.status = "pendiente"

    order.payment_id = str(payment.get("id") or "")
    order.save(update_fields=["status", "payment_id", "updated_at"])

    if order.status == "completada":
        grant_order_access(order)

    return order


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
@parser_classes([MultiPartParser, FormParser])
def admin_image_upload_view(request):
    image = request.FILES.get("image")
    if not image:
        return Response({"error": "Falta la imagen."}, status=status.HTTP_400_BAD_REQUEST)

    if not image.content_type.startswith("image/"):
        return Response({"error": "El archivo debe ser una imagen."}, status=status.HTTP_400_BAD_REQUEST)

    if image.size > settings.CLOUDINARY_MAX_UPLOAD_BYTES:
        return Response({"error": "La imagen supera el tamano maximo permitido."}, status=status.HTTP_400_BAD_REQUEST)

    credentials = get_cloudinary_credentials()
    if not credentials:
        return Response(
            {"error": "Configura Cloudinary en Ajustes antes de subir imagenes."},
            status=status.HTTP_409_CONFLICT,
        )

    timestamp = int(time.time())
    upload_params = {
        "timestamp": timestamp,
        "folder": settings.CLOUDINARY_UPLOAD_FOLDER,
    }
    signature = sign_cloudinary_upload(upload_params, credentials["api_secret"])
    upload_url = f"https://api.cloudinary.com/v1_1/{credentials['cloud_name']}/image/upload"

    try:
        response = requests.post(
            upload_url,
            data={
                **{key: value for key, value in upload_params.items() if value},
                "api_key": credentials["api_key"],
                "signature": signature,
            },
            files={"file": (image.name, image.file, image.content_type)},
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.error("Cloudinary image upload request failed: %s", exc, exc_info=True)
        return Response({"error": "No se pudo subir la imagen."}, status=status.HTTP_502_BAD_GATEWAY)

    if response.status_code >= 400:
        message = cloudinary_error(response, "Cloudinary rechazo la imagen.")
        logger.error(
            "Cloudinary image upload rejected: status=%s message=%s body=%s",
            response.status_code,
            message,
            response.text[:1000],
        )
        return Response(
            {"error": message},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        data = response.json()
    except ValueError:
        logger.error(
            "Cloudinary image upload returned non-JSON response: status=%s body=%s",
            response.status_code,
            response.text[:1000],
        )
        return Response(
            {"error": "Cloudinary devolvio una respuesta invalida."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    secure_url = data.get("secure_url")
    if not secure_url:
        logger.error("Cloudinary image upload response without secure_url: %s", data)
        return Response({"error": "Cloudinary no devolvio una URL valida."}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(
        {
            "url": secure_url,
            "publicId": data.get("public_id"),
            "resourceType": data.get("resource_type"),
            "bytes": data.get("bytes"),
            "format": data.get("format"),
        }
    )


VALID_DOWNLOAD_TYPES = {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}

VALID_DOWNLOAD_EXTENSIONS = {".pdf", ".zip"}


def get_r2_client():
    if not all([
        settings.R2_ACCOUNT_ID,
        settings.R2_ACCESS_KEY_ID,
        settings.R2_SECRET_ACCESS_KEY,
        settings.R2_BUCKET_NAME,
        settings.R2_PUBLIC_BASE_URL,
    ]):
        return None
    import boto3
    endpoint_url = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
    )


def safe_filename(filename):
    name = Path(filename).name
    safe = "".join(c for c in name if c.isalnum() or c in "._- ")
    return safe or "download"


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
@parser_classes([MultiPartParser, FormParser])
def admin_download_upload_view(request):
    file = request.FILES.get("file")
    if not file:
        return Response({"error": "Falta el archivo."}, status=status.HTTP_400_BAD_REQUEST)

    extension = Path(file.name).suffix.lower()
    content_type = (file.content_type or "").lower()

    type_valid = content_type in VALID_DOWNLOAD_TYPES or extension in VALID_DOWNLOAD_EXTENSIONS
    ext_valid = extension in VALID_DOWNLOAD_EXTENSIONS
    if not type_valid or not ext_valid:
        return Response(
            {"error": "El archivo debe ser PDF o ZIP."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if file.size > settings.DOWNLOAD_MAX_BYTES:
        return Response(
            {"error": "El archivo supera el maximo permitido de 100 MB."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not all([
        settings.R2_ACCOUNT_ID,
        settings.R2_ACCESS_KEY_ID,
        settings.R2_SECRET_ACCESS_KEY,
        settings.R2_BUCKET_NAME,
        settings.R2_PUBLIC_BASE_URL,
    ]):
        return Response(
            {"error": "Falta configurar Cloudflare R2 en el servidor."},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        client = get_r2_client()
    except Exception as exc:
        logger.error("Failed to initialize R2 client: %s", exc, exc_info=True)
        return Response(
            {"error": "Falta configurar Cloudflare R2 en el servidor."},
            status=status.HTTP_409_CONFLICT,
        )

    file.seek(0)
    object_key = f"{settings.R2_DOWNLOAD_PREFIX}/{uuid4()}-{safe_filename(file.name)}"

    try:
        client.upload_fileobj(
            file,
            settings.R2_BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
    except Exception as exc:
        logger.error("R2 upload failed", exc_info=True)
        return Response(
            {"error": "No se pudo subir el archivo a R2."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    download_url = f"{settings.R2_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"

    return Response(
        {
            "url": download_url,
            "fileName": file.name,
            "objectKey": object_key,
            "contentType": file.content_type,
            "bytes": file.size,
            "storage": "r2",
        }
    )


class ProductListCreateView(generics.ListCreateAPIView):
    queryset = Product.objects.filter(is_active=True).order_by("-created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProductSerializer
        return ProductListSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsEnvAdmin()]
        return [AllowAny()]


class ProductDetailUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    lookup_field = "pk"

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ProductListSerializer
        return ProductSerializer

    def get_permissions(self):
        if self.request.method in ["PUT", "PATCH", "DELETE"]:
            return [IsEnvAdmin()]
        return [AllowAny()]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()


class AdminProductListCreateView(ProductListCreateView):
    permission_classes = [IsEnvAdmin]

    def get_serializer_class(self):
        return ProductSerializer

    def get_permissions(self):
        return [IsEnvAdmin()]


class AdminProductDetailUpdateDestroyView(ProductDetailUpdateDestroyView):
    permission_classes = [IsEnvAdmin]

    def get_serializer_class(self):
        return ProductSerializer

    def get_permissions(self):
        return [IsEnvAdmin()]


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_order_list_view(request):
    orders = Order.objects.all().order_by("-created_at")[:100]
    serializer = OrderSerializer(orders, many=True)
    return Response({"orders": serializer.data})


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_dashboard_stats_view(request):
    products = Product.objects.filter(is_active=True)
    orders = Order.objects.all()
    completed_orders = orders.filter(status="completada")
    revenue = completed_orders.aggregate(total=Sum("total"))["total"] or Decimal("0")
    sold_units = OrderItem.objects.filter(order__status="completada").aggregate(
        total=Sum("quantity")
    )["total"] or 0

    categories = (
        Category.objects.annotate(product_count=Count("products", filter=Q(products__is_active=True)))
        .filter(product_count__gt=0)
        .order_by("-product_count", "name")
    )
    status_counts = orders.values("status").annotate(count=Count("id")).order_by("status")
    top_products = (
        OrderItem.objects.filter(order__status="completada")
        .values("product_id", "product__title")
        .annotate(quantity=Sum("quantity"), revenue=Sum("price"))
        .order_by("-quantity")[:5]
    )

    return Response(
        {
            "summary": {
                "products": products.count(),
                "featuredProducts": products.filter(featured=True).count(),
                "categories": categories.count(),
                "orders": orders.count(),
                "completedOrders": completed_orders.count(),
                "soldUnits": sold_units,
                "revenue": str(revenue),
                "productsWithImages": products.exclude(image="").count(),
                "productsWithDownloads": products.exclude(download_url="").count(),
            },
            "categories": [
                {
                    "slug": category.slug,
                    "name": category.name,
                    "count": category.product_count,
                }
                for category in categories[:8]
            ],
            "orderStatuses": [
                {"status": row["status"], "count": row["count"]}
                for row in status_counts
            ],
            "topProducts": [
                {
                    "id": row["product_id"],
                    "title": row["product__title"],
                    "quantity": row["quantity"],
                    "revenue": str(row["revenue"] or "0"),
                }
                for row in top_products
            ],
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def library_view(request):
    purchases = (
        PurchasedProduct.objects.filter(user=request.user, is_active=True)
        .select_related("product", "order", "product__category")
        .order_by("-acquired_at")
    )
    serializer = PurchasedProductSerializer(purchases, many=True)
    return Response({"items": serializer.data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def library_download_view(request, pk):
    purchase = get_object_or_404(
        PurchasedProduct.objects.select_related("product"),
        user=request.user,
        product_id=pk,
        is_active=True,
    )
    if not purchase.product.download_url:
        return Response(
            {"error": "Este producto todavia no tiene archivo descargable."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "downloadUrl": purchase.product.download_url,
            "downloadFileName": purchase.product.download_filename,
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def order_list_create_view(request):
    if request.method == "GET":
        orders = Order.objects.filter(user=request.user).order_by("-created_at")
        serializer = OrderSerializer(orders, many=True)
        return Response({"orders": serializer.data})

    serializer = OrderSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    customer = request.data.get("customer", {})
    customer_name = customer.get("name", "").strip()
    customer_email = customer.get("email", "").lower().strip()

    if not customer_name or not customer_email:
        return Response({"error": "Datos de cliente incompletos."}, status=status.HTTP_400_BAD_REQUEST)

    order = serializer.save(
        user=request.user,
        customer_name=customer_name,
        customer_email=customer_email,
    )
    return Response({"order": OrderSerializer(order).data}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_detail_view(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not request.user.is_admin and order.customer_email != request.user.email:
        return Response({"error": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
    return Response({"order": OrderSerializer(order).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_payment_preference_view(request):
    items_data = request.data.get("items", [])
    customer = request.data.get("customer", {})
    customer_name = customer.get("name", "").strip() or request.user.first_name
    customer_email = request.user.email.lower().strip()

    if not items_data or not customer_name or not customer_email:
        return Response({"error": "Datos incompletos."}, status=status.HTTP_400_BAD_REQUEST)

    order_items = []
    for item in items_data:
        try:
            product = Product.objects.get(id=item["productId"], is_active=True)
            quantity = int(item.get("quantity", 1))
            if quantity < 1:
                raise ValueError
            order_items.append({"product": product, "quantity": quantity})
        except (Product.DoesNotExist, ValueError, KeyError):
            return Response({"error": f"Item inválido: {item}"}, status=status.HTTP_400_BAD_REQUEST)

    total = sum(item["product"].price * item["quantity"] for item in order_items)

    order = Order.objects.create(
        user=request.user,
        total=total,
        status="completada" if not settings.MP_ACCESS_TOKEN else "pendiente",
        customer_name=customer_name,
        customer_email=customer_email,
        external_reference="",
    )
    order.external_reference = str(order.id)
    order.save(update_fields=["external_reference", "updated_at"])

    for item in order_items:
        OrderItem.objects.create(
            order=order,
            product=item["product"],
            quantity=item["quantity"],
            price=item["product"].price,
        )

    base_url = normalize_frontend_url(settings.FRONTEND_URL)
    backend_url = get_backend_public_url(request)

    if settings.MP_ACCESS_TOKEN and not settings.DEBUG:
        if not base_url.startswith("https://"):
            return Response(
                {"error": "FRONTEND_URL debe ser HTTPS para Mercado Pago en produccion."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if not backend_url.startswith("https://"):
            return Response(
                {"error": "BACKEND_PUBLIC_URL debe ser HTTPS para recibir webhooks de Mercado Pago."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    if not settings.MP_ACCESS_TOKEN:
        grant_order_access(order)
        return Response({
            "demo": True,
            "orderId": str(order.id),
            "init_point": f"{base_url}/checkout/success?order_id={order.id}",
        })

    mercado_pago_mode = get_mercado_pago_mode()
    if mercado_pago_mode == "production" and str(settings.MP_ACCESS_TOKEN).strip().startswith("TEST-"):
        order.status = "fallida"
        order.save(update_fields=["status", "updated_at"])
        return Response(
            {
                "error": (
                    "Mercado Pago esta configurado como produccion, pero MP_ACCESS_TOKEN es de prueba. "
                    "Para cobrar real usa el Access Token productivo APP_USR de la cuenta vendedora. "
                    "Para pruebas, configura MP_MODE=test y usa usuarios/tarjetas de prueba."
                ),
                "mpMode": mercado_pago_mode,
            },
            status=status.HTTP_409_CONFLICT,
        )

    notification_url = get_payment_notification_url(request)
    preference_payload = {
        "items": [
            {
                "id": str(item["product"].id),
                "title": item["product"].title,
                "unit_price": float(item["product"].price),
                "quantity": item["quantity"],
                "currency_id": "ARS",
            }
            for item in order_items
        ],
        "payer": {"name": customer_name, "email": customer_email},
        "back_urls": {
            "success": f"{base_url}/checkout/success",
            "failure": f"{base_url}/checkout/failure",
            "pending": f"{base_url}/checkout/failure",
        },
        "auto_return": "approved",
        "external_reference": str(order.id),
        "notification_url": notification_url,
        "metadata": {
            "order_id": str(order.id),
            "user_id": str(request.user.id),
        },
    }
    preference_client = get_mercado_pago_sdk().preference()
    result = preference_client.create(preference_payload)

    response_body = result.get("response", {})
    status_code = int(result.get("status") or 500)
    used_return_urls_fallback = False
    if status_code >= 400 and is_mercado_pago_back_urls_error(response_body):
        logger.warning(
            "Mercado Pago rejected back_urls. Retrying without return URLs. "
            "status=%s response=%s back_urls=%s notification_url=%s",
            status_code,
            response_body,
            preference_payload.get("back_urls"),
            notification_url,
        )
        fallback_payload = {
            key: value
            for key, value in preference_payload.items()
            if key not in {"back_urls", "auto_return"}
        }
        result = preference_client.create(fallback_payload)
        response_body = result.get("response", {})
        status_code = int(result.get("status") or 500)
        used_return_urls_fallback = status_code < 400

    if status_code >= 400:
        logger.warning(
            "Mercado Pago preference creation failed. status=%s response=%s "
            "back_urls=%s notification_url=%s",
            status_code,
            response_body,
            preference_payload.get("back_urls"),
            notification_url,
        )
        order.status = "fallida"
        order.save(update_fields=["status", "updated_at"])
        return Response(
            {
                "error": mercado_pago_error_message(response_body),
                "mpStatus": status_code,
                "mpCause": response_body.get("cause") if isinstance(response_body, dict) else [],
            },
            status=mercado_pago_response_status(status_code, response_body),
        )

    order.preference_id = response_body.get("id") or ""
    order.save(update_fields=["preference_id", "updated_at"])

    init_point = get_mercado_pago_checkout_url(response_body, mercado_pago_mode)
    if not init_point:
        return Response(
            {
                "error": "Mercado Pago no devolvio un link de pago valido.",
                "mpMode": mercado_pago_mode,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({
        "init_point": init_point,
        "orderId": str(order.id),
        "preferenceId": order.preference_id,
        "notificationUrl": notification_url,
        "returnUrlsFallback": used_return_urls_fallback,
        "mpMode": mercado_pago_mode,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def payment_webhook_view(request):
    payment_id = extract_mercado_pago_payment_id(request)
    if not payment_id:
        return Response({"ok": True, "ignored": "missing_payment_id"})

    if not validate_mercado_pago_webhook_signature(request, payment_id):
        return Response({"error": "Firma de Mercado Pago invalida."}, status=status.HTTP_401_UNAUTHORIZED)

    if not settings.MP_ACCESS_TOKEN:
        return Response({"ok": True, "ignored": "missing_mp_access_token"})

    payment, error = get_mercado_pago_payment(payment_id)
    if error:
        return Response({"ok": True, "warning": error})

    order = update_order_from_mercado_pago_payment(payment)
    return Response({
        "ok": True,
        "paymentId": str(payment.get("id") or payment_id),
        "orderId": str(order.id) if order else "",
        "orderStatus": order.status if order else "",
    })
