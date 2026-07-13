import os
import json
import hashlib
import time
import base64
import secrets
import logging
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse
import zipfile
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
from django.db.models import Count, DecimalField, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
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
    Notification,
    Order,
    OrderItem,
    PasswordResetRequest,
    Payment,
    PaymentEvent,
    PendingRegistration,
    Product,
    PurchasedProduct,
    UserEvent,
    UserProfile,
    WorkbookDraft,
)
from .serializers import (
    ChangePasswordSerializer,
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
    _canonical_admin_username,
    clear_admin_cookie,
    create_admin_token,
    get_admin_from_request,
    set_admin_cookie,
    verify_admin_credentials,
)
from .email_service import (
    EmailDeliveryError,
    read_email_verification_token,
    send_abandoned_cart_email,
    send_download_help_email,
    send_download_ready_email,
    send_new_product_email,
    send_password_reset_code_email,
    send_product_updated_email,
    send_purchase_confirmation_email,
    send_registration_code_email,
    send_support_received_email,
    send_verification_email,
    send_welcome_email,
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
    token = AccessToken.for_user(user)
    token["token_version"] = user.auth_token_version
    return str(token)


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


def _record_event(user, event_type, entity_type="", entity_id="", metadata=None):
    try:
        UserEvent.objects.create(
            user=user,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else "",
            metadata=metadata or {},
        )
    except Exception:
        logger.exception("Failed to record event %s for user %s", event_type, user)


ORDER_STATUS_MAP = {
    "pendiente": "pending",
    "completada": "approved",
    "fallida": "rejected",
    "reembolsada": "refunded",
}


def map_order_status(internal_status):
    return ORDER_STATUS_MAP.get(internal_status, "pending")


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
        _record_event(user, "account_registered", "user", user.id)
        _record_event(user, "email_verified", "user", user.id)

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
        user.auth_token_version += 1
        user.save(update_fields=["password", "email_verified", "email_verified_at", "auth_token_version", "updated_at"])

        now = timezone.now()
        PasswordResetRequest.objects.filter(
            user=user,
            used_at__isnull=True,
        ).update(used_at=now, updated_at=now)
        _record_event(user, "password_reset", "user", user.id)

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
        _record_event(user, "email_verified", "user", user.id)

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

    if not user.is_active or user.disabled_at is not None:
        return Response({"error": "La cuenta esta deshabilitada."}, status=status.HTTP_403_FORBIDDEN)

    if not user.email_verified:
        response = Response(
            {
                "error": "Este email todavia no esta verificado. Volve a registrarte para recibir un codigo nuevo."
            },
            status=status.HTTP_403_FORBIDDEN,
        )
        return clear_auth_cookie(response)

    user.last_login = timezone.now()
    user.save(update_fields=["last_login", "updated_at"])
    _record_event(user, "login")

    token = make_auth_token(user)
    response = Response({"user": UserSerializer(user).data, "accessToken": token})
    return set_auth_cookie(response, user, token)


@api_view(["GET"])
def me_view(request):
    if request.user.is_authenticated:
        return Response({"user": UserSerializer(request.user).data})
    return Response({"user": None})


def _build_admin_response(username):
    """Build structured admin data dict from a canonical username/email."""
    if not username:
        return None
    try:
        user = User.objects.get(email__iexact=username, is_admin=True)
        return {
            "id": str(user.id),
            "username": user.email,
            "name": user.first_name or user.email.split("@")[0],
            "email": user.email,
            "role": "admin",
        }
    except User.DoesNotExist:
        return {
            "id": None,
            "username": username,
            "name": username.split("@")[0] if "@" in username else username,
            "email": username,
            "role": "admin",
        }


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_login_view(request):
    username = request.data.get("username") or ""
    password = request.data.get("password", "")

    if not username or not password:
        return Response(
            {"error": "ADMIN_UNAUTHORIZED", "message": "Usuario y contrasena son obligatorios.", "details": None},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not verify_admin_credentials(username, password):
        return Response(
            {"error": "ADMIN_UNAUTHORIZED", "message": "Credenciales de administracion incorrectas.", "details": None},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    canonical = _canonical_admin_username(username) or username
    token = create_admin_token(username)
    admin_data = _build_admin_response(canonical)
    response = Response(
        {
            "admin": {
                "username": username,
                "id": (admin_data or {}).get("id"),
                "name": (admin_data or {}).get("name"),
                "email": (admin_data or {}).get("email"),
                "role": "admin",
            },
            "adminToken": token,
            "token": token,
            "accessToken": token,
        }
    )
    return set_admin_cookie(response, token)


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_logout_view(request):
    response = Response({"success": True})
    return clear_admin_cookie(response)


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_me_view(request):
    admin_info = get_admin_from_request(request)
    if not admin_info:
        return Response(
            {"error": "ADMIN_UNAUTHORIZED", "message": "No se pudo autenticar la solicitud.", "details": None},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    admin_data = _build_admin_response(admin_info["username"])
    return Response({"admin": admin_data})


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

    notification = Notification.objects.filter(
        order=order,
        type="purchase_confirmed",
    ).order_by("-created_at").first()
    if notification and notification.status == "sent":
        return
    if not notification:
        notification = _create_notification(
            "purchase_confirmed",
            order.customer_email,
            user=order.user,
            order=order,
        )

    try:
        result = send_purchase_confirmation_email(order, notification=notification)
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
        return bool(
            settings.DEBUG
            and getattr(settings, "MP_ALLOW_UNSIGNED_WEBHOOKS_IN_DEBUG", False)
        )

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
            "contentType": image.content_type,
            "bytes": data.get("bytes"),
            "resourceType": data.get("resource_type"),
            "format": data.get("format"),
        }
    )


def extract_cloudinary_public_id(url=None, public_id=None):
    if public_id:
        pid = public_id.strip()
    elif url:
        cloud_name = "res.cloudinary.com"
        if cloud_name not in url:
            return None
        from urllib.parse import unquote, urlparse as up
        parsed = up(unquote(url))
        path = parsed.path.lstrip("/")
        parts = path.split("/")
        try:
            upload_idx = parts.index("upload")
        except ValueError:
            return None
        version_and_after = parts[upload_idx + 1:]
        version_removed = [p for p in version_and_after if not (p.startswith("v") and p[1:].isdigit())]
        pid = "/".join(version_removed)
        dot = pid.rfind(".")
        if dot > pid.rfind("/"):
            pid = pid[:dot]
    else:
        return None

    if not pid:
        return None

    prefix = settings.CLOUDINARY_UPLOAD_FOLDER
    if not pid.startswith(prefix):
        return None

    if any(c in pid for c in ["..", "//", "\\"]):
        return None

    return pid


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_image_delete_view(request):
    url = request.data.get("url", "").strip()
    public_id = request.data.get("publicId", "").strip()

    pid = extract_cloudinary_public_id(url=url or None, public_id=public_id or None)
    if not pid:
        return Response(
            {"error": "No se pudo identificar la imagen en Cloudinary."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    credentials = get_cloudinary_credentials()
    if not credentials:
        return Response(
            {"error": "Configura Cloudinary en Ajustes antes de eliminar imagenes."},
            status=status.HTTP_409_CONFLICT,
        )

    timestamp = int(time.time())
    destroy_params = {
        "public_id": pid,
        "timestamp": timestamp,
        "invalidate": "true",
    }
    signature = sign_cloudinary_upload(destroy_params, credentials["api_secret"])
    destroy_url = f"https://api.cloudinary.com/v1_1/{credentials['cloud_name']}/image/destroy"

    logger.info("Cloudinary image delete requested: public_id=%s", pid)

    try:
        response = requests.post(
            destroy_url,
            data={
                "public_id": pid,
                "timestamp": timestamp,
                "invalidate": "true",
                "api_key": credentials["api_key"],
                "signature": signature,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.error("Cloudinary image delete request failed: %s", exc, exc_info=True)
        return Response(
            {"error": "No se pudo eliminar la imagen de Cloudinary."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not response.ok:
        logger.error(
            "Cloudinary image delete rejected: status=%s body=%s",
            response.status_code,
            response.text[:1000],
        )
        return Response(
            {"error": "No se pudo eliminar la imagen de Cloudinary."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        result = response.json()
    except ValueError:
        logger.error(
            "Cloudinary image delete non-JSON response: status=%s body=%s",
            response.status_code,
            response.text[:1000],
        )
        return Response(
            {"error": "No se pudo eliminar la imagen de Cloudinary."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    result_status = result.get("result")
    if result_status == "not found":
        return Response({
            "ok": True,
            "deleted": False,
            "publicId": pid,
            "message": "La imagen ya no existia en Cloudinary.",
        })

    if result_status != "ok":
        logger.error("Cloudinary image delete unexpected result: %s", result)
        return Response(
            {"error": "No se pudo eliminar la imagen de Cloudinary."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({
        "ok": True,
        "deleted": True,
        "publicId": pid,
    })


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
    logger.info("Download upload request started")
    file = request.FILES.get("file")
    if not file:
        return Response({"error": "Falta el archivo."}, status=status.HTTP_400_BAD_REQUEST)

    logger.info(
        "Download upload file received: name=%s size=%s content_type=%s",
        file.name,
        file.size,
        file.content_type,
    )

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
            "publicId": object_key,
            "contentType": file.content_type,
            "bytes": file.size,
            "storage": "r2",
        }
    )


def extract_r2_object_key(url=None, object_key=None):
    if object_key:
        key = object_key.strip().lstrip("/")
    elif url:
        base = settings.R2_PUBLIC_BASE_URL.rstrip("/")
        if not url.startswith(base):
            return None
        from urllib.parse import unquote
        key = unquote(url[len(base):].lstrip("/"))
    else:
        return None

    if not key:
        return None

    prefix = settings.R2_DOWNLOAD_PREFIX
    if not key.startswith(prefix):
        return None

    return key


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_download_delete_view(request):
    url = request.data.get("url", "").strip()
    object_key = request.data.get("objectKey", "").strip()

    key = extract_r2_object_key(url=url or None, object_key=object_key or None)
    if not key:
        return Response(
            {"error": "No se pudo identificar el archivo en R2."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not all([
        settings.R2_ACCOUNT_ID,
        settings.R2_ACCESS_KEY_ID,
        settings.R2_SECRET_ACCESS_KEY,
        settings.R2_BUCKET_NAME,
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

    logger.info("R2 download delete requested: key=%s", key)

    try:
        client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        exists = True
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if error_code == "NotFound" or getattr(exc, "__class__.__name__", "") == "ClientError":
            exists = False
        else:
            logger.error("R2 delete failed", exc_info=True)
            return Response(
                {"error": "No se pudo eliminar el archivo de R2."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    if not exists:
        return Response(
            {
                "ok": True,
                "deleted": False,
                "objectKey": key,
                "message": "El archivo ya no existia en R2.",
            }
        )

    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    except Exception as exc:
        logger.error("R2 delete failed", exc_info=True)
        return Response(
            {"error": "No se pudo eliminar el archivo de R2."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({
        "ok": True,
        "deleted": True,
        "objectKey": key,
    })


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
    pending_orders = orders.filter(status="pendiente")
    failed_orders = orders.filter(status="fallida")
    refunded_orders = orders.filter(status="reembolsada")
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

    response = Response(
        {
            "generatedAt": timezone.now(),
            "summary": {
                "products": products.count(),
                "featuredProducts": products.filter(featured=True).count(),
                "categories": categories.count(),
                "orders": orders.count(),
                "purchases": completed_orders.count(),
                "completedOrders": completed_orders.count(),
                "pendingOrders": pending_orders.count(),
                "failedOrders": failed_orders.count(),
                "refundedOrders": refunded_orders.count(),
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
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_dashboard_view(request):
    now = timezone.now()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    active_products = Product.objects.filter(is_active=True)
    all_orders = Order.objects.all()

    sales_this_month = (
        all_orders.filter(status="completada", created_at__gte=first_of_month)
        .aggregate(total=Sum("total"))["total"]
        or Decimal("0")
    )

    downloads_count = UserEvent.objects.filter(
        event_type="material_downloaded"
    ).count()

    recent_orders = (
        Order.objects.select_related("user")
        .order_by("-created_at")[:5]
    )
    recent_products = active_products.order_by("-created_at")[:5]

    return Response(
        {
            "salesThisMonth": str(sales_this_month),
            "ordersCount": all_orders.count(),
            "productsCount": active_products.count(),
            "downloadsCount": downloads_count if downloads_count > 0 else None,
            "salesTrend": [],
            "recentOrders": [
                {
                    "id": str(o.id),
                    "customerName": o.customer_name,
                    "total": str(o.total),
                    "status": o.status,
                    "createdAt": o.created_at,
                }
                for o in recent_orders
            ],
            "recentProducts": [
                {
                    "id": str(p.id),
                    "title": p.title,
                    "price": str(p.price),
                    "image": p.image,
                    "isActive": p.is_active,
                    "createdAt": p.created_at,
                }
                for p in recent_products
            ],
        }
    )


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_order_detail_view(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("user").prefetch_related("items__product", "payments"),
        pk=pk,
    )
    serializer = OrderSerializer(order)
    data = serializer.data
    data["customer"] = {"name": order.customer_name, "email": order.customer_email}
    latest_payment = order.payments.order_by("-updated_at").first()
    data["paymentId"] = latest_payment.provider_payment_id if latest_payment else None
    data["preferenceId"] = order.preference_id
    data["externalReference"] = order.external_reference
    return Response({"order": data})


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_files_view(request):
    products_with_downloads = (
        Product.objects
        .exclude(download_url="")
        .order_by("-created_at")
        .values(
            "id", "title", "download_url", "download_filename",
            "download_content_type", "download_size", "created_at",
        )
    )
    items = []
    for p in products_with_downloads:
        items.append({
            "id": str(p["id"]),
            "productId": str(p["id"]),
            "productTitle": p["title"],
            "fileName": p["download_filename"] or None,
            "fileType": (
                "pdf" if "pdf" in (p["download_content_type"] or "")
                else "zip" if "zip" in (p["download_content_type"] or "")
                else None
            ),
            "mimeType": p["download_content_type"] or None,
            "size": p["download_size"],
            "url": p["download_url"],
            "createdAt": p["created_at"],
        })
    return Response({"items": items})


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_settings_view(request):
    from .cloudinary_settings import get_saved_cloudinary_settings
    from .nvidia_settings import get_saved_nvidia_settings

    cloud_settings = get_saved_cloudinary_settings()
    nv_settings = get_saved_nvidia_settings()

    cloud_configured = bool(
        cloud_settings
        or (settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY)
    )
    nv_configured = bool(
        nv_settings
        or settings.NVIDIA_API_KEY
    )
    r2_configured = bool(
        settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_BUCKET_NAME
        and settings.R2_PUBLIC_BASE_URL
    )

    result = {
        "cloudinary": {
            "configured": cloud_configured,
            "cloudName": (
                cloud_settings.cloud_name
                if cloud_settings and cloud_settings.cloud_name
                else (settings.CLOUDINARY_CLOUD_NAME if cloud_configured else None)
            ),
        },
        "nvidia": {
            "configured": nv_configured,
            "model": (
                nv_settings.model
                if nv_settings and nv_settings.model
                else (settings.NVIDIA_MODEL if nv_configured else None)
            ),
        },
        "storage": {
            "configured": r2_configured,
            "provider": "r2" if r2_configured else None,
        },
    }
    return Response(result)


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

    _record_event(
        request.user,
        "material_downloaded",
        entity_type="product",
        entity_id=str(pk),
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
    _record_event(request.user, "checkout_started", "order", order.id)

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
            "success": f"{base_url}/checkout/success?order_id={order.id}",
            "failure": f"{base_url}/checkout/failure?order_id={order.id}",
            "pending": f"{base_url}/checkout/pending?order_id={order.id}",
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
    try:
        result = preference_client.create(preference_payload)
    except Exception:
        logger.exception("Mercado Pago preference creation raised an exception for order %s", order.id)
        order.status = "fallida"
        order.save(update_fields=["status", "updated_at"])
        return Response(
            {"error": "No se pudo iniciar el pago. Intenta nuevamente."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    response_body = result.get("response", {})
    status_code = int(result.get("status") or 500)

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
        order.status = "fallida"
        order.save(update_fields=["status", "updated_at"])
        return Response(
            {
                "error": "Mercado Pago no devolvio un link de pago valido.",
                "mpMode": mercado_pago_mode,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    _record_event(request.user, "payment_pending", "order", order.id)

    return Response({
        "init_point": init_point,
        "orderId": str(order.id),
        "preferenceId": order.preference_id,
        "notificationUrl": notification_url,
        "mpMode": mercado_pago_mode,
    })


def _create_notification(notification_type, recipient, user=None, order=None, metadata=None):
    notification = Notification.objects.create(
        user=user,
        order=order,
        type=notification_type,
        channel="email",
        recipient=recipient,
        status="pending",
        metadata=metadata or {},
    )
    if user:
        _record_event(user, "email_queued", "notification", notification.id)
    return notification


def _deliver_purchase_notification(order, notification):
    if not notification or notification.status != "pending":
        return
    try:
        result = send_purchase_confirmation_email(order, notification=notification)
        if result.get("sent"):
            if not order.purchase_email_sent_at:
                order.purchase_email_sent_at = timezone.now()
                order.save(update_fields=["purchase_email_sent_at", "updated_at"])
    except EmailDeliveryError:
        return


def _webhook_event_identity(request, payment_id):
    payload = request.data if isinstance(request.data, dict) else {}
    action = str(payload.get("action") or "payment.updated")[:100]
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    provider_event_id = str(
        payload.get("id")
        or request.headers.get("x-request-id")
        or f"{payment_id}:{action}:{payload_hash}"
    )[:200]
    return provider_event_id, action, payload_hash


def _complete_order(order, payment_data):
    if order.status == "completada":
        return Notification.objects.filter(
            order=order,
            type="purchase_confirmed",
        ).order_by("-created_at").first()

    now = timezone.now()
    order.status = "completada"
    order.payment_id = str(payment_data.get("id") or "")
    order.paid_at = now
    order.save(update_fields=["status", "payment_id", "paid_at", "updated_at"])

    for item in order.items.select_related("product"):
        PurchasedProduct.objects.update_or_create(
            user=order.user,
            product=item.product,
            defaults={"order": order, "is_active": True},
        )

    _record_event(order.user, "payment_approved", "order", order.id)
    _record_event(order.user, "library_access_granted", "order", order.id)
    return _create_notification(
        "purchase_confirmed",
        order.customer_email,
        user=order.user,
        order=order,
    )


def _finish_payment_event(event, *, processed=True, error_message=""):
    event.processed = processed
    event.error_message = str(error_message or "")[:500]
    event.processed_at = timezone.now() if processed else None
    event.save(update_fields=["processed", "error_message", "processed_at"])


@api_view(["POST"])
@permission_classes([AllowAny])
def payment_webhook_view(request):
    payment_id = extract_mercado_pago_payment_id(request)
    if not payment_id:
        return Response({"error": "Falta data.id."}, status=status.HTTP_400_BAD_REQUEST)

    if not validate_mercado_pago_webhook_signature(request, payment_id):
        return Response({"error": "Firma de Mercado Pago invalida."}, status=status.HTTP_401_UNAUTHORIZED)

    if not settings.MP_ACCESS_TOKEN:
        return Response(
            {"error": "Mercado Pago no esta configurado."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    provider_event_id, action, payload_hash = _webhook_event_identity(request, payment_id)
    event, created = PaymentEvent.objects.get_or_create(
        provider="mercadopago",
        provider_event_id=provider_event_id,
        defaults={
            "provider_payment_id": str(payment_id),
            "event_type": "webhook_received",
            "action": action,
            "payload_hash": payload_hash,
        },
    )
    if not created and event.processed:
        return Response({"ok": True, "duplicate": True})

    payment_data, error = get_mercado_pago_payment(payment_id)
    if error:
        _finish_payment_event(event, processed=False, error_message=error)
        return Response(
            {"error": "No se pudo consultar el pago."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    external_reference = str(payment_data.get("external_reference") or "").strip()
    if not external_reference:
        external_reference = str((payment_data.get("metadata") or {}).get("order_id") or "").strip()
    if not external_reference:
        _finish_payment_event(event, error_message="missing_external_reference")
        return Response({"ok": True, "ignored": "missing_external_reference"})

    try:
        amount = Decimal(str(payment_data["transaction_amount"]))
        currency = str(payment_data["currency_id"])
    except (KeyError, TypeError, ValueError):
        _finish_payment_event(event, error_message="missing_payment_totals")
        return Response({"ok": True, "ignored": "missing_payment_totals"})

    payment_status = str(payment_data.get("status") or "").lower()
    notification = None

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=external_reference)

            if amount != order.total:
                _finish_payment_event(event, error_message="amount_mismatch")
                return Response({"ok": True, "ignored": "amount_mismatch"})
            if currency != "ARS":
                _finish_payment_event(event, error_message="currency_mismatch")
                return Response({"ok": True, "ignored": "currency_mismatch"})

            preference_id = str(
                payment_data.get("preference_id")
                or (payment_data.get("order") or {}).get("id")
                or ""
            )
            if order.preference_id and preference_id != str(order.preference_id):
                _finish_payment_event(event, error_message="preference_mismatch")
                return Response({"ok": True, "ignored": "preference_mismatch"})

            existing_payment = Payment.objects.filter(
                provider_payment_id=str(payment_id)
            ).first()
            if existing_payment and existing_payment.order_id != order.id:
                _finish_payment_event(event, error_message="payment_already_linked")
                return Response({"ok": True, "ignored": "payment_already_linked"})

            approved_at = existing_payment.approved_at if existing_payment else None
            if payment_status == "approved" and approved_at is None:
                approved_at = timezone.now()

            payment, _ = Payment.objects.update_or_create(
                provider_payment_id=str(payment_id),
                defaults={
                    "order": order,
                    "provider": "mercadopago",
                    "preference_id": preference_id,
                    "status": payment_status,
                    "status_detail": str(payment_data.get("status_detail") or ""),
                    "amount": amount,
                    "currency": currency,
                    "payer_email": str((payment_data.get("payer") or {}).get("email") or ""),
                    "approved_at": approved_at,
                    "raw_metadata": {
                        "payment_method_id": payment_data.get("payment_method_id"),
                        "payment_type_id": payment_data.get("payment_type_id"),
                        "installments": payment_data.get("installments"),
                    },
                },
            )

            if payment_status == "approved":
                notification = _complete_order(order, payment_data)
            elif payment_status in {"refunded", "charged_back"}:
                order.status = "reembolsada"
                order.payment_id = str(payment_id)
                order.save(update_fields=["status", "payment_id", "updated_at"])
                _record_event(order.user, "payment_refunded", "order", order.id)
            elif order.status == "completada":
                pass
            elif payment_status in {"rejected", "cancelled"}:
                order.status = "fallida"
                order.payment_id = str(payment_id)
                order.save(update_fields=["status", "payment_id", "updated_at"])
                _record_event(order.user, "payment_rejected", "order", order.id)
            else:
                order.status = "pendiente"
                order.payment_id = str(payment_id)
                order.save(update_fields=["status", "payment_id", "updated_at"])
                _record_event(order.user, "payment_pending", "order", order.id)

            event.event_type = "payment_processed"
            event.action = payment_status
            _finish_payment_event(event)
    except (Order.DoesNotExist, ValueError):
        _finish_payment_event(event, error_message="invalid_external_reference")
        return Response({"ok": True, "ignored": "invalid_external_reference"})

    if payment_status == "approved":
        _deliver_purchase_notification(order, notification)

    return Response({
        "ok": True,
        "paymentId": str(payment_id),
        "orderId": str(order.id),
        "orderStatus": map_order_status(order.status),
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    new_password = serializer.validated_data["newPassword"]

    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    try:
        validate_password(new_password, user)
    except ValidationError as exc:
        return Response({"error": {"newPassword": exc.messages}}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        user.set_password(new_password)
        user.auth_token_version += 1
        user.save(update_fields=["password", "auth_token_version", "updated_at"])

    _record_event(user, "password_changed")

    response = Response({"ok": True, "message": "Contrasena actualizada. Inicia sesion nuevamente."})
    return clear_auth_cookie(response)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_status_view(request, pk):
    order = get_object_or_404(Order.objects.select_related("user"), pk=pk)
    if order.user_id != request.user.id and not request.user.is_admin:
        return Response({"error": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)

    has_library_access = PurchasedProduct.objects.filter(
        order=order, is_active=True
    ).exists()

    latest_notification = Notification.objects.filter(order=order, type="purchase_confirmed").order_by("-created_at").first()
    email_status = latest_notification.status if latest_notification else None
    latest_payment = order.payments.order_by("-updated_at").first()
    public_status = map_order_status(order.status)
    redirects = {
        "approved": "/perfil?payment=approved",
        "pending": f"/checkout/pending?order_id={order.id}",
        "rejected": f"/checkout/failure?order_id={order.id}",
        "refunded": "/perfil?payment=refunded",
    }

    return Response({
        "orderId": str(order.id),
        "status": public_status,
        "paymentStatus": latest_payment.status if latest_payment else None,
        "libraryReady": has_library_access,
        "emailStatus": email_status,
        "redirectTo": redirects[public_status],
        "updatedAt": order.updated_at,
    })


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def avatar_view(request):
    if request.method == "DELETE":
        return _avatar_delete(request)
    return _avatar_update(request)


def _avatar_update(request):
    user = request.user
    image = request.FILES.get("avatar")
    if not image:
        return Response({"error": "Falta el archivo de avatar."}, status=status.HTTP_400_BAD_REQUEST)

    if not image.content_type.startswith("image/"):
        return Response({"error": "El archivo debe ser una imagen (JPEG, PNG o WebP)."}, status=status.HTTP_400_BAD_REQUEST)

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type not in allowed_types:
        return Response({"error": "Formato no soportado. Usa JPEG, PNG o WebP."}, status=status.HTTP_400_BAD_REQUEST)

    max_bytes = getattr(settings, "CLOUDINARY_AVATAR_MAX_BYTES", 5 * 1024 * 1024)
    if image.size > max_bytes:
        return Response({"error": f"La imagen supera el maximo de {max_bytes // (1024*1024)} MB."}, status=status.HTTP_400_BAD_REQUEST)

    from PIL import Image as PilImage
    try:
        pil_image = PilImage.open(image)
        pil_image.verify()
        image.seek(0)
    except Exception:
        return Response({"error": "El contenido del archivo no es una imagen valida."}, status=status.HTTP_400_BAD_REQUEST)

    credentials = get_cloudinary_credentials()
    if not credentials:
        return Response(
            {"error": "Configura Cloudinary en Ajustes antes de subir imagenes."},
            status=status.HTTP_409_CONFLICT,
        )

    profile, _ = UserProfile.objects.get_or_create(user=user)
    old_public_id = profile.avatar_public_id

    avatar_folder = f"{settings.CLOUDINARY_AVATAR_FOLDER.rstrip('/')}/{user.id}"
    timestamp = int(time.time())
    upload_params = {
        "timestamp": timestamp,
        "folder": avatar_folder,
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
        logger.error("Cloudinary avatar upload failed: %s", exc, exc_info=True)
        return Response({"error": "No se pudo subir el avatar."}, status=status.HTTP_502_BAD_GATEWAY)

    if response.status_code >= 400:
        message = cloudinary_error(response, "Cloudinary rechazo la imagen.")
        logger.error("Cloudinary avatar upload rejected: %s", message)
        return Response({"error": message}, status=status.HTTP_502_BAD_GATEWAY)

    try:
        data = response.json()
    except ValueError:
        return Response({"error": "Cloudinary devolvio una respuesta invalida."}, status=status.HTTP_502_BAD_GATEWAY)

    secure_url = data.get("secure_url")
    if not secure_url:
        return Response({"error": "Cloudinary no devolvio una URL valida."}, status=status.HTTP_502_BAD_GATEWAY)

    profile.avatar_url = secure_url
    profile.avatar_public_id = data.get("public_id", "")
    profile.save(update_fields=["avatar_url", "avatar_public_id", "updated_at"])

    if old_public_id:
        _cloudinary_delete_image(old_public_id)

    _record_event(user, "avatar_updated")

    return Response({
        "avatarUrl": secure_url,
    })


def _avatar_delete(request):
    user = request.user
    profile = getattr(user, "profile", None)
    if not profile or not profile.avatar_public_id:
        return Response({"ok": True, "deleted": False, "message": "No hay avatar para eliminar."})

    public_id = profile.avatar_public_id
    if not _cloudinary_delete_image(public_id):
        return Response(
            {"error": "No se pudo eliminar el avatar de Cloudinary."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    profile.avatar_url = ""
    profile.avatar_public_id = ""
    profile.save(update_fields=["avatar_url", "avatar_public_id", "updated_at"])

    _record_event(user, "avatar_deleted")

    return Response({"ok": True, "deleted": True})


# --- Admin: Users ---


def _admin_user_data(user):
    profile = getattr(user, "profile", None)
    orders_count = getattr(user, "metric_orders_count", None)
    completed_orders_count = getattr(user, "metric_completed_orders_count", None)
    total_spent = getattr(user, "metric_total_spent", None)
    last_order_at = getattr(user, "metric_last_order_at", None)
    library_count = getattr(user, "metric_library_count", None)
    emails_sent = getattr(user, "metric_emails_sent", None)
    emails_failed = getattr(user, "metric_emails_failed", None)

    if orders_count is None:
        orders_count = user.orders.count()
        completed_orders = user.orders.filter(status="completada")
        completed_orders_count = completed_orders.count()
        total_spent = completed_orders.aggregate(total=Sum("total"))["total"] or Decimal("0")
        last_order = user.orders.order_by("-created_at").first()
        last_order_at = last_order.created_at if last_order else None
        library_count = PurchasedProduct.objects.filter(user=user, is_active=True).count()
        emails_sent = Notification.objects.filter(user=user, status="sent").count()
        emails_failed = Notification.objects.filter(user=user, status="failed").count()

    return {
        "id": str(user.id),
        "name": user.first_name or user.email.split("@")[0],
        "email": user.email,
        "avatarUrl": profile.avatar_url if profile else "",
        "emailVerified": user.email_verified,
        "isActive": user.is_active,
        "createdAt": user.created_at,
        "lastLoginAt": user.last_login,
        "ordersCount": orders_count,
        "completedOrdersCount": completed_orders_count,
        "totalSpent": str(total_spent),
        "lastOrderAt": last_order_at,
        "libraryItemsCount": library_count,
        "emailsSentCount": emails_sent,
        "emailsFailedCount": emails_failed,
    }


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_users_list_view(request):
    try:
        page = max(1, int(request.query_params.get("page", "1")))
        page_size = min(100, max(1, int(request.query_params.get("pageSize", "20"))))
    except (TypeError, ValueError):
        return Response(
            {"error": "page y pageSize deben ser numeros enteros positivos."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    search = request.query_params.get("search", "").strip()
    email_verified = request.query_params.get("emailVerified", "").strip()
    status_filter = request.query_params.get("status", "").strip()
    has_purchases = request.query_params.get("hasPurchases", "").strip()
    ordering = request.query_params.get("ordering", "-created_at").strip()

    order_metrics = Order.objects.filter(user_id=OuterRef("pk")).values("user_id")
    completed_metrics = order_metrics.filter(status="completada")
    purchase_metrics = PurchasedProduct.objects.filter(
        user_id=OuterRef("pk"), is_active=True
    ).values("user_id")
    sent_metrics = Notification.objects.filter(
        user_id=OuterRef("pk"), status="sent"
    ).values("user_id")
    failed_metrics = Notification.objects.filter(
        user_id=OuterRef("pk"), status="failed"
    ).values("user_id")

    queryset = User.objects.select_related("profile").annotate(
        metric_orders_count=Coalesce(
            Subquery(order_metrics.annotate(value=Count("id")).values("value")[:1]),
            Value(0),
            output_field=IntegerField(),
        ),
        metric_completed_orders_count=Coalesce(
            Subquery(completed_metrics.annotate(value=Count("id")).values("value")[:1]),
            Value(0),
            output_field=IntegerField(),
        ),
        metric_total_spent=Coalesce(
            Subquery(
                completed_metrics.annotate(value=Sum("total")).values("value")[:1],
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        metric_last_order_at=Subquery(
            Order.objects.filter(user_id=OuterRef("pk"))
            .order_by("-created_at")
            .values("created_at")[:1]
        ),
        metric_library_count=Coalesce(
            Subquery(purchase_metrics.annotate(value=Count("id")).values("value")[:1]),
            Value(0),
            output_field=IntegerField(),
        ),
        metric_emails_sent=Coalesce(
            Subquery(sent_metrics.annotate(value=Count("id")).values("value")[:1]),
            Value(0),
            output_field=IntegerField(),
        ),
        metric_emails_failed=Coalesce(
            Subquery(failed_metrics.annotate(value=Count("id")).values("value")[:1]),
            Value(0),
            output_field=IntegerField(),
        ),
    )

    if search:
        queryset = queryset.filter(
            Q(email__icontains=search) | Q(first_name__icontains=search)
        )
    if email_verified == "true":
        queryset = queryset.filter(email_verified=True)
    elif email_verified == "false":
        queryset = queryset.filter(email_verified=False)
    if status_filter == "active":
        queryset = queryset.filter(is_active=True)
    elif status_filter == "disabled":
        queryset = queryset.filter(is_active=False)
    if has_purchases == "true":
        queryset = queryset.filter(purchased_products__is_active=True).distinct()
    elif has_purchases == "false":
        queryset = queryset.exclude(purchased_products__is_active=True).distinct()

    valid_ordering = {"created_at", "-created_at", "email", "-email", "last_login", "-last_login"}
    if ordering not in valid_ordering:
        ordering = "-created_at"
    queryset = queryset.order_by(ordering)

    total_items = queryset.count()
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = min(page, total_pages)

    start = (page - 1) * page_size
    end = start + page_size
    users_page = queryset[start:end]

    return Response({
        "items": [_admin_user_data(u) for u in users_page],
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "totalItems": total_items,
            "totalPages": total_pages,
        },
    })


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_user_detail_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    profile = getattr(user, "profile", None)
    recent_orders = user.orders.order_by("-created_at")[:10]
    payments = Payment.objects.filter(order__user=user).order_by("-created_at")[:10]
    library = PurchasedProduct.objects.filter(user=user, is_active=True).select_related("product", "order")[:20]
    notifications = Notification.objects.filter(user=user).order_by("-created_at")[:20]
    events = UserEvent.objects.filter(user=user)[:50]

    return Response({
        "user": _admin_user_data(user),
        "profile": {
            "avatarUrl": profile.avatar_url if profile else "",
            "phone": profile.phone if profile else "",
        } if profile else None,
        "recentOrders": [
            {
                "id": str(o.id),
                "total": str(o.total),
                "status": o.status,
                "createdAt": o.created_at,
            }
            for o in recent_orders
        ],
        "payments": [
            {
                "id": str(p.id),
                "providerPaymentId": p.provider_payment_id,
                "status": p.status,
                "amount": str(p.amount),
                "createdAt": p.created_at,
            }
            for p in payments
        ],
        "library": [
            {
                "id": str(pp.id),
                "productTitle": pp.product.title,
                "productId": str(pp.product.id),
                "acquiredAt": pp.acquired_at,
            }
            for pp in library
        ],
        "notifications": NotificationSerializer(notifications, many=True).data,
        "events": UserEventSerializer(events, many=True).data,
    })


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_user_orders_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    orders = user.orders.order_by("-created_at")
    return Response({
        "items": OrderSerializer(orders, many=True).data,
    })


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_user_events_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    events = UserEvent.objects.filter(user=user)
    return Response({
        "items": UserEventSerializer(events, many=True).data,
    })


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_user_notifications_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    notifications = Notification.objects.filter(user=user).order_by("-created_at")
    return Response({
        "items": NotificationSerializer(notifications, many=True).data,
    })


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_user_library_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    library = PurchasedProduct.objects.filter(user=user, is_active=True).select_related("product", "order")
    return Response({
        "items": PurchasedProductSerializer(library, many=True).data,
    })


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_order_resend_email_view(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if order.status != "completada":
        return Response({"error": "La orden no esta completada."}, status=status.HTTP_400_BAD_REQUEST)

    notification = _create_notification(
        notification_type="purchase_confirmed",
        recipient=order.customer_email,
        user=order.user,
        order=order,
    )

    try:
        result = send_purchase_confirmation_email(order, notification=notification)
        if result.get("sent"):
            if not order.purchase_email_sent_at:
                order.purchase_email_sent_at = timezone.now()
                order.save(update_fields=["purchase_email_sent_at", "updated_at"])
            return Response({"ok": True, "sent": True})
        return Response({"ok": True, "sent": False, "reason": result.get("reason", "")})
    except EmailDeliveryError as exc:
        return Response({"ok": False, "sent": False, "error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


@api_view(["POST"])
def logout_view(request):
    if request.user.is_authenticated:
        _record_event(request.user, "logout")
    response = Response({"ok": True})
    return clear_auth_cookie(response)


# --- Import Bundle ---

VALID_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
COVER_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".avif": "image/avif",
}
ZIP_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".pif", ".sh", ".bin", ".app"}
BUNDLE_SCHEMA_VERSION = "paola-product-bundle-v1"
VALID_LEVELS = {"Inicial", "Intermedio", "Avanzado"}


def _upload_image_to_cloudinary_from_bytes(file_bytes, filename, content_type):
    credentials = get_cloudinary_credentials()
    if not credentials:
        raise ValueError("Configura Cloudinary en Ajustes antes de subir imagenes.")

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
            files={"file": (filename, BytesIO(file_bytes), content_type)},
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.error("Cloudinary upload request failed: %s", exc, exc_info=True)
        raise ValueError("No se pudo conectar con Cloudinary.") from exc

    if response.status_code >= 400:
        msg = cloudinary_error(response, "Cloudinary rechazo la imagen.")
        raise ValueError(msg)

    data = response.json()
    secure_url = data.get("secure_url")
    if not secure_url:
        raise ValueError("Cloudinary no devolvio una URL valida.")

    return {"url": secure_url, "publicId": data.get("public_id")}


def _cloudinary_delete_image(public_id):
    if not public_id:
        return False
    credentials = get_cloudinary_credentials()
    if not credentials:
        return False

    timestamp = int(time.time())
    destroy_params = {
        "public_id": public_id,
        "timestamp": timestamp,
        "invalidate": "true",
    }
    signature = sign_cloudinary_upload(destroy_params, credentials["api_secret"])
    destroy_url = f"https://api.cloudinary.com/v1_1/{credentials['cloud_name']}/image/destroy"

    try:
        response = requests.post(
            destroy_url,
            data={
                "public_id": public_id,
                "timestamp": timestamp,
                "invalidate": "true",
                "api_key": credentials["api_key"],
                "signature": signature,
            },
            timeout=30,
        )
        return response.ok and response.json().get("result") == "ok"
    except Exception:
        logger.exception("Cloudinary rollback delete failed for public_id=%s", public_id)
        return False


def _upload_download_to_r2_from_bytes(file_bytes, filename, content_type):
    client = get_r2_client()
    if not client:
        raise ValueError("Falta configurar Cloudflare R2 en el servidor.")

    safe_name = safe_filename(filename)
    object_key = f"{settings.R2_DOWNLOAD_PREFIX}/{uuid4()}-{safe_name}"

    buf = BytesIO(file_bytes)
    try:
        client.upload_fileobj(
            buf,
            settings.R2_BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
    except Exception as exc:
        logger.error("R2 upload failed", exc_info=True)
        raise ValueError("No se pudo subir el archivo a R2.") from exc

    download_url = f"{settings.R2_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"

    return {
        "url": download_url,
        "fileName": filename,
        "objectKey": object_key,
        "publicId": object_key,
        "contentType": content_type,
        "bytes": len(file_bytes),
        "storage": "r2",
    }


def _r2_delete_object(object_key):
    if not object_key:
        return False
    client = get_r2_client()
    if not client:
        return False
    try:
        client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=object_key)
    except Exception:
        return False
    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=object_key)
        return True
    except Exception:
        logger.exception("R2 rollback delete failed for key=%s", object_key)
        return False


MAX_GALLERY_IMAGES = 6
MAX_PREVIEW_BASE64_BYTES = 2 * 1024 * 1024  # 2 MB per image dataUrl


def _file_to_data_url(file_bytes, content_type):
    if not file_bytes or len(file_bytes) > MAX_PREVIEW_BASE64_BYTES:
        return None
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _find_file_in_zip(zf, target_filename):
    target = Path(target_filename).name
    for name in zf.namelist():
        if Path(name).name == target:
            return name
    return None


def _cleanup_cloudinary_uploads(public_ids):
    for pid in public_ids:
        if pid:
            try:
                _cloudinary_delete_image(pid)
            except Exception:
                logger.exception("Cloudinary cleanup failed for public_id=%s", pid)


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
@parser_classes([MultiPartParser, FormParser])
def admin_product_import_bundle_preview_view(request):
    zip_file = request.FILES.get("file")
    if not zip_file:
        return Response({"error": "Falta el archivo ZIP."}, status=status.HTTP_400_BAD_REQUEST)
    if not zip_file.name.lower().endswith(".zip"):
        return Response({"error": "El archivo debe tener extension .zip."}, status=status.HTTP_400_BAD_REQUEST)
    if zip_file.size > ZIP_MAX_BYTES:
        return Response({"error": "El archivo ZIP supera el maximo permitido de 50 MB."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        zip_data = zip_file.read()
        zf = zipfile.ZipFile(BytesIO(zip_data))
    except zipfile.BadZipFile:
        return Response({"error": "El archivo ZIP esta corrupto o no es valido."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        for name in zf.namelist():
            normalized = Path(name).as_posix()
            if normalized.startswith("/") or ".." in normalized.split("/"):
                return Response({"error": f"El ZIP contiene rutas no seguras: {name}"}, status=status.HTTP_400_BAD_REQUEST)
            ext = Path(name).suffix.lower()
            if ext in EXECUTABLE_EXTENSIONS:
                return Response({"error": f"El ZIP contiene archivos ejecutables: {name}"}, status=status.HTTP_400_BAD_REQUEST)

        manifest_files = [n for n in zf.namelist() if Path(n).name == "manifest.json"]
        if not manifest_files:
            return Response({"error": "El ZIP debe contener un manifest.json en la raiz."}, status=status.HTTP_400_BAD_REQUEST)
        manifest_name = manifest_files[0]
        for n in manifest_files:
            if Path(n).parent == Path("."):
                manifest_name = n
                break
        try:
            manifest_data = json.loads(zf.read(manifest_name))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response({"error": "manifest.json no es un JSON valido."}, status=status.HTTP_400_BAD_REQUEST)

        schema_version = manifest_data.get("schemaVersion", "")
        if schema_version != BUNDLE_SCHEMA_VERSION:
            return Response({"error": f"Version de esquema no soportada: '{schema_version}'."}, status=status.HTTP_400_BAD_REQUEST)

        product_raw = manifest_data.get("product")
        if not isinstance(product_raw, dict):
            product_raw = manifest_data
        assets_raw = manifest_data.get("assets")
        if not isinstance(assets_raw, dict):
            assets_raw = manifest_data

        title = (product_raw.get("title") or "").strip()
        description = (product_raw.get("description") or "").strip()
        category_slug = (product_raw.get("category") or "").strip()
        price = product_raw.get("price")
        compare_at_price = product_raw.get("compareAtPrice")
        age = (product_raw.get("age") or "").strip()
        level = (product_raw.get("level") or "").strip()
        badge = (product_raw.get("badge") or "").strip() or None
        featured = bool(product_raw.get("featured", False))
        features = product_raw.get("features", [])
        objectives = product_raw.get("objectives", [])
        cover_path = (assets_raw.get("coverImage") or "").strip()
        download_path = (assets_raw.get("downloadFile") or "").strip()
        gallery_manifest = assets_raw.get("galleryImages", [])

        warnings = []
        errors = {}

        def _add_error(k, m):
            errors[k] = m

        if not title: _add_error("manifest.product.title", "El titulo es obligatorio.")
        if not description: _add_error("manifest.product.description", "La descripcion es obligatoria.")
        if not category_slug: _add_error("manifest.product.category", "La categoria es obligatoria.")
        if price is None or price == "": _add_error("manifest.product.price", "El precio es obligatorio.")
        if not age: _add_error("manifest.product.age", "La edad es obligatoria.")
        if not level: _add_error("manifest.product.level", "El nivel es obligatorio.")
        if not cover_path: _add_error("manifest.assets.coverImage", "El archivo de portada es obligatorio.")
        if not download_path: _add_error("manifest.assets.downloadFile", "El archivo descargable es obligatorio.")
        if errors:
            return Response({"error": errors}, status=status.HTTP_400_BAD_REQUEST)

        if level not in VALID_LEVELS:
            return Response({"error": f"Nivel no valido: '{level}'."}, status=status.HTTP_400_BAD_REQUEST)

        cover_file_name = Path(cover_path).name
        cover_ext = Path(cover_file_name).suffix.lower()
        if cover_ext not in VALID_COVER_EXTENSIONS:
            return Response({"error": f"Formato de portada no soportado: '{cover_ext}'."}, status=status.HTTP_400_BAD_REQUEST)

        cover_entry = _find_file_in_zip(zf, cover_path)
        if not cover_entry:
            return Response({"error": f"Archivo de portada no encontrado: '{cover_path}'."}, status=status.HTTP_400_BAD_REQUEST)

        download_file_name = Path(download_path).name
        download_ext = Path(download_file_name).suffix.lower()
        if download_ext not in {".pdf", ".zip"}:
            return Response({"error": "El archivo descargable debe ser PDF o ZIP."}, status=status.HTTP_400_BAD_REQUEST)

        download_entry = _find_file_in_zip(zf, download_path)
        if not download_entry:
            return Response({"error": f"Archivo descargable no encontrado: '{download_path}'."}, status=status.HTTP_400_BAD_REQUEST)

        cover_bytes = zf.read(cover_entry)
        download_bytes = zf.read(download_entry)

        cover_ct = COVER_MIME_MAP.get(cover_ext, "image/png")
        cover_data_url = _file_to_data_url(cover_bytes, cover_ct)

        # Build gallery preview entries
        gallery_previews = []
        if isinstance(gallery_manifest, list):
            valid_gallery_exts = {".png", ".jpg", ".jpeg", ".webp"}
            for idx, img_path in enumerate(gallery_manifest):
                if idx >= MAX_GALLERY_IMAGES:
                    warnings.append(f"Se ignoraron {len(gallery_manifest) - MAX_GALLERY_IMAGES} imagen(es) de galeria (maximo {MAX_GALLERY_IMAGES}).")
                    break
                img_path_s = str(img_path).strip()
                if not img_path_s:
                    continue
                img_entry = _find_file_in_zip(zf, img_path_s)
                if not img_entry:
                    return Response({"error": f"Imagen de galeria no encontrada en el ZIP: '{img_path_s}'."}, status=status.HTTP_400_BAD_REQUEST)
                img_name = Path(img_path_s).name
                img_ext = Path(img_name).suffix.lower()
                if img_ext not in valid_gallery_exts:
                    return Response({"error": f"Formato de galeria no soportado: '{img_path_s}'."}, status=status.HTTP_400_BAD_REQUEST)
                img_bytes = zf.read(img_entry)
                img_ct = COVER_MIME_MAP.get(img_ext, "image/png")
                gallery_previews.append({
                    "path": img_path_s,
                    "fileName": img_name,
                    "contentType": img_ct,
                    "size": len(img_bytes),
                    "dataUrl": _file_to_data_url(img_bytes, img_ct),
                    "order": idx + 1,
                })
    finally:
        zf.close()

    download_ct = "application/pdf" if download_ext == ".pdf" else "application/zip"
    download_display_name = (assets_raw.get("downloadFileName") or "").strip() or download_file_name

    return Response({
        "preview": {
            "product": {
                "title": title,
                "description": description,
                "price": price,
                "compareAtPrice": compare_at_price,
                "category": category_slug,
                "level": level,
                "age": age,
                "badge": badge,
                "featured": featured,
                "features": features if isinstance(features, list) else [],
                "objectives": objectives if isinstance(objectives, list) else [],
            },
            "assets": {
                "coverImage": {
                    "path": cover_path,
                    "fileName": cover_file_name,
                    "contentType": cover_ct,
                    "size": len(cover_bytes),
                    "dataUrl": cover_data_url,
                },
                "galleryImages": gallery_previews,
                "downloadFile": {
                    "path": download_path,
                    "fileName": download_display_name,
                    "contentType": download_ct,
                    "size": len(download_bytes),
                },
            },
        },
        "warnings": warnings,
    })


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
@parser_classes([MultiPartParser, FormParser])
def admin_product_import_bundle_view(request):
    zip_file = request.FILES.get("file")
    if not zip_file:
        return Response({"error": "Falta el archivo ZIP."}, status=status.HTTP_400_BAD_REQUEST)

    if not zip_file.name.lower().endswith(".zip"):
        return Response({"error": "El archivo debe tener extension .zip."}, status=status.HTTP_400_BAD_REQUEST)

    if zip_file.size > ZIP_MAX_BYTES:
        return Response(
            {"error": "El archivo ZIP supera el maximo permitido de 50 MB."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        zip_data = zip_file.read()
        zf = zipfile.ZipFile(BytesIO(zip_data))
    except zipfile.BadZipFile:
        return Response(
            {"error": "El archivo ZIP esta corrupto o no es valido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        for name in zf.namelist():
            normalized = Path(name).as_posix()
            if normalized.startswith("/") or ".." in normalized.split("/"):
                return Response(
                    {"error": f"El archivo ZIP contiene rutas no seguras: {name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ext = Path(name).suffix.lower()
            if ext in EXECUTABLE_EXTENSIONS:
                return Response(
                    {"error": f"El archivo ZIP contiene archivos ejecutables no permitidos: {name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        manifest_files = [name for name in zf.namelist() if Path(name).name == "manifest.json"]
        if not manifest_files:
            return Response(
                {"error": "El ZIP debe contener un archivo manifest.json en la raiz."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        manifest_name = manifest_files[0]
        for name in manifest_files:
            if Path(name).parent == Path("."):
                manifest_name = name
                break

        try:
            manifest_data = json.loads(zf.read(manifest_name))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                {"error": "manifest.json no es un JSON valido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        schema_version = manifest_data.get("schemaVersion", "")
        if schema_version != BUNDLE_SCHEMA_VERSION:
            return Response(
                {"error": f"Version de esquema no soportada: '{schema_version}'. Se espera '{BUNDLE_SCHEMA_VERSION}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Read product and assets from manifest (nested structure)
        product_raw = manifest_data.get("product")
        if not isinstance(product_raw, dict):
            product_raw = manifest_data  # fallback to legacy flat format
        assets_raw = manifest_data.get("assets")
        if not isinstance(assets_raw, dict):
            assets_raw = manifest_data  # fallback to legacy flat format

        # Apply overrides from request (if any)
        overrides_raw = request.data.get("overrides")
        if overrides_raw:
            try:
                overrides_data = json.loads(overrides_raw) if isinstance(overrides_raw, str) else overrides_raw
            except (json.JSONDecodeError, TypeError):
                return Response(
                    {"error": "overrides debe ser un JSON valido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not isinstance(overrides_data, dict):
                return Response(
                    {"error": "overrides debe ser un objeto JSON."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if "assets" in overrides_data:
                return Response(
                    {"error": "overrides.assets no esta permitido. Los assets se leen del ZIP."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if isinstance(overrides_data.get("product"), dict):
                merged_product = dict(product_raw)
                override_product = overrides_data["product"]
                allowed_override_keys = {"title", "description", "price", "compareAtPrice", "category", "level", "age", "badge", "featured", "features", "objectives"}
                for key, value in override_product.items():
                    if key in allowed_override_keys:
                        merged_product[key] = value
                product_raw = merged_product

        title = (product_raw.get("title") or "").strip()
        description = (product_raw.get("description") or "").strip()
        category_slug = (product_raw.get("category") or "").strip()
        price = product_raw.get("price")
        compare_at_price = product_raw.get("compareAtPrice")
        age = (product_raw.get("age") or "").strip()
        level = (product_raw.get("level") or "").strip()
        badge = (product_raw.get("badge") or "").strip() or None
        featured = bool(product_raw.get("featured", False))
        features = product_raw.get("features", [])
        objectives = product_raw.get("objectives", [])
        cover_path = (assets_raw.get("coverImage") or "").strip()
        download_path = (assets_raw.get("downloadFile") or "").strip()
        gallery_manifest = assets_raw.get("galleryImages", [])

        warnings = []
        errors = {}

        def _add_error(field_key, message):
            errors[field_key] = message

        if not title:
            _add_error("manifest.product.title", "El titulo es obligatorio.")
        if not description:
            _add_error("manifest.product.description", "La descripcion es obligatoria.")
        if not category_slug:
            _add_error("manifest.product.category", "La categoria es obligatoria.")
        if price is None or price == "":
            _add_error("manifest.product.price", "El precio es obligatorio.")
        if not age:
            _add_error("manifest.product.age", "La edad es obligatoria.")
        if not level:
            _add_error("manifest.product.level", "El nivel es obligatorio.")
        if not cover_path:
            _add_error("manifest.assets.coverImage", "El archivo de portada es obligatorio.")
        if not download_path:
            _add_error("manifest.assets.downloadFile", "El archivo descargable es obligatorio.")

        if errors:
            return Response({"error": errors}, status=status.HTTP_400_BAD_REQUEST)

        if level not in VALID_LEVELS:
            return Response(
                {"error": f"Nivel no valido: '{level}'. Debe ser uno de: {', '.join(sorted(VALID_LEVELS))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cover_file_name = Path(cover_path).name
        cover_ext = Path(cover_file_name).suffix.lower()
        if cover_ext not in VALID_COVER_EXTENSIONS:
            return Response(
                {"error": f"Formato de portada no soportado: '{cover_ext}'. Usa: {', '.join(sorted(VALID_COVER_EXTENSIONS))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cover_name = None
        for name in zf.namelist():
            if Path(name).name == cover_file_name:
                cover_name = name
                break
        if not cover_name:
            return Response(
                {"error": f"Archivo de portada no encontrado en el ZIP: '{cover_path}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        download_file_name = Path(download_path).name
        download_ext = Path(download_file_name).suffix.lower()
        if download_ext not in {".pdf", ".zip"}:
            return Response(
                {"error": "El archivo descargable debe ser PDF o ZIP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        download_name = None
        for name in zf.namelist():
            if Path(name).name == download_file_name:
                download_name = name
                break
        if not download_name:
            return Response(
                {"error": f"Archivo descargable no encontrado en el ZIP: '{download_path}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        download_display_name = (assets_raw.get("downloadFileName") or "").strip()
        if not download_display_name:
            download_display_name = download_file_name

        cover_bytes = zf.read(cover_name)
        download_bytes = zf.read(download_name)

        # Read gallery image bytes while ZIP is still open
        gallery_uploads = []
        valid_gallery_exts = {".png", ".jpg", ".jpeg", ".webp"}
        if isinstance(gallery_manifest, list):
            for idx, img_path in enumerate(gallery_manifest):
                if idx >= MAX_GALLERY_IMAGES:
                    warnings.append(f"Se ignoraron {len(gallery_manifest) - MAX_GALLERY_IMAGES} imagenes de galeria (maximo {MAX_GALLERY_IMAGES}).")
                    break
                img_path_s = str(img_path).strip()
                if not img_path_s:
                    continue
                img_entry = _find_file_in_zip(zf, img_path_s)
                if not img_entry:
                    return Response({"error": f"Imagen de galeria no encontrada en el ZIP: '{img_path_s}'."}, status=status.HTTP_400_BAD_REQUEST)
                img_name = Path(img_path_s).name
                img_ext = Path(img_name).suffix.lower()
                if img_ext not in valid_gallery_exts:
                    return Response({"error": f"Formato de galeria no soportado: '{img_path_s}'."}, status=status.HTTP_400_BAD_REQUEST)
                img_bytes = zf.read(img_entry)
                img_ct = COVER_MIME_MAP.get(img_ext, "image/png")
                gallery_uploads.append((img_path_s, img_name, img_ct, img_bytes, idx + 1))
    finally:
        zf.close()

    cover_content_type = COVER_MIME_MAP.get(cover_ext, "image/png")
    download_content_type = "application/pdf" if download_ext == ".pdf" else "application/zip"

    uploaded_cloudinary_public_ids: list[str] = []
    uploaded_r2_object_key = None

    try:
        # 1. Upload cover to Cloudinary
        cloudinary_result = _upload_image_to_cloudinary_from_bytes(
            cover_bytes, cover_file_name, cover_content_type
        )
        uploaded_cloudinary_public_ids.append(cloudinary_result["publicId"])

        # 2. Upload gallery images to Cloudinary
        gallery_results = []
        for img_path_s, img_name, img_ct, img_bytes, order in gallery_uploads:
            img_result = _upload_image_to_cloudinary_from_bytes(img_bytes, img_name, img_ct)
            uploaded_cloudinary_public_ids.append(img_result["publicId"])
            gallery_results.append({
                "url": img_result["url"],
                "publicId": img_result["publicId"],
                "fileName": img_name,
                "order": order,
                "sourcePath": img_path_s,
            })

        # 3. Upload download file to R2
        r2_result = _upload_download_to_r2_from_bytes(
            download_bytes, download_file_name, download_content_type
        )
        uploaded_r2_object_key = r2_result["objectKey"]

        # 4. Build product payload
        product_payload = {
            "title": title,
            "description": description,
            "price": str(price),
            "compare_at_price": str(compare_at_price) if compare_at_price else None,
            "category": category_slug,
            "image": cloudinary_result["url"],
            "image_public_id": cloudinary_result["publicId"],
            "download_url": r2_result["url"],
            "download_filename": download_display_name or download_file_name,
            "download_public_id": r2_result["objectKey"],
            "download_content_type": download_content_type,
            "download_size": len(download_bytes),
            "badge": badge,
            "featured": featured,
            "age": age,
            "level": level,
            "features": features if isinstance(features, list) else [],
            "objectives": objectives if isinstance(objectives, list) else [],
            "metadata": {
                "imported_from_zip": True,
                "bundle_schema_version": schema_version,
            },
        }
        if gallery_results:
            product_payload["metadata"]["gallery_images"] = gallery_results

        serializer = ProductSerializer(data=product_payload)
        if not serializer.is_valid():
            _cleanup_cloudinary_uploads(uploaded_cloudinary_public_ids)
            if uploaded_r2_object_key:
                _r2_delete_object(uploaded_r2_object_key)
            return Response(
                {"error": serializer.errors, "created": False},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = serializer.save()

        return Response(
            {
                "created": True,
                "product": serializer.data,
                "uploads": {
                    "image": cloudinary_result,
                    "gallery": gallery_results,
                    "download": r2_result,
                },
                "warnings": warnings,
            },
            status=status.HTTP_201_CREATED,
        )

    except ValueError as exc:
        _cleanup_cloudinary_uploads(uploaded_cloudinary_public_ids)
        if uploaded_r2_object_key:
            _r2_delete_object(uploaded_r2_object_key)
        return Response(
            {"error": str(exc), "created": False},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    except Exception as exc:
        _cleanup_cloudinary_uploads(uploaded_cloudinary_public_ids)
        if uploaded_r2_object_key:
            _r2_delete_object(uploaded_r2_object_key)
        logger.error("Import bundle unexpected error: %s", exc, exc_info=True)
        return Response(
            {"error": "Error inesperado al importar el producto."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
