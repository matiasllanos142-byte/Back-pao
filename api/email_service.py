import logging
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core import signing
from django.utils.html import escape

from .email_templates import render_email_template

logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_SALT = "paola-psicope.email-verification"


class EmailDeliveryError(Exception):
    pass


def make_email_verification_token(user):
    return signing.dumps(
        {"user_id": str(user.id), "email": user.email},
        salt=EMAIL_VERIFICATION_SALT,
    )


def read_email_verification_token(token):
    return signing.loads(
        token,
        salt=EMAIL_VERIFICATION_SALT,
        max_age=settings.EMAIL_VERIFICATION_TOKEN_TTL_SECONDS,
    )


def build_email_verification_url(user, request=None):
    token = make_email_verification_token(user)
    path = f"/api/auth/verify-email?token={token}"

    if settings.BACKEND_PUBLIC_URL:
        return f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}{path}"

    if request is not None:
        return request.build_absolute_uri(path)

    return path


def normalize_public_frontend_url(value):
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

    custom_domains = [
        candidate
        for candidate in candidates
        if "up.railway.app" not in urlparse(candidate).netloc
    ]
    return custom_domains[0] if custom_domains else candidates[0]


def build_frontend_url(path):
    base_url = normalize_public_frontend_url(settings.FRONTEND_URL)
    return f"{base_url}{path}"


def send_resend_email(message):
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY is not configured; email was not sent.")
        return {"sent": False, "id": None, "reason": "missing_api_key"}

    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [message["to"]],
        "subject": message["subject"],
        "html": message["html"],
        "text": message["text"],
    }
    if settings.RESEND_REPLY_TO:
        payload["reply_to"] = settings.RESEND_REPLY_TO

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "paola-psicope-backend/1.0",
            },
            json=payload,
            timeout=settings.RESEND_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise EmailDeliveryError("No se pudo conectar con Resend.") from exc

    if response.status_code >= 400:
        reason = "Resend rechazo el envio del email."
        try:
            data = response.json()
            if data.get("message"):
                reason = data["message"]
        except ValueError:
            pass

        logger.warning(
            "Resend rejected email with status %s: %s",
            response.status_code,
            response.text[:500],
        )
        raise EmailDeliveryError(reason)

    data = response.json()
    return {"sent": True, "id": data.get("id"), "reason": None}


def send_purchase_confirmation_email(order):
    items = list(order.items.select_related("product"))
    first_product = items[0].product.title if items else "Material comprado"
    order_url = build_frontend_url(f"/perfil#biblioteca")

    rendered = render_email_template("purchase_confirmed", {
        "name": order.customer_name or "familia",
        "order_id": f"#{str(order.id)[:8]}",
        "product_title": first_product,
        "total": f"$ {order.total}",
        "payment_status": "Aprobado",
        "order_url": order_url,
    })

    return send_resend_email(
        {
            "to": order.customer_email,
            "subject": rendered["subject"],
            "html": rendered["html"],
            "text": rendered["text"],
        }
    )


def send_verification_email(user, request=None):
    verification_url = build_email_verification_url(user, request)
    name = user.first_name or user.email.split("@")[0] if user.email else "familia"

    rendered = render_email_template("verify_account", {
        "name": name,
        "code": "",
        "verify_url": verification_url,
        "expires_minutes": "1440",
        "subject": "Confirmá tu cuenta en Paola Psicopé",
    })

    return send_resend_email(
        {
            "to": user.email,
            "subject": rendered["subject"],
            "html": rendered["html"],
            "text": rendered["text"],
        }
    )


def send_registration_code_email(name, email, code):
    expires_minutes = int(settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS / 60) if hasattr(settings, "EMAIL_VERIFICATION_CODE_TTL_SECONDS") else 10
    rendered = render_email_template("verify_account", {
        "name": name or "familia",
        "code": code,
        "expires_minutes": str(expires_minutes),
    })

    return send_resend_email(
        {
            "to": email,
            "subject": rendered["subject"],
            "html": rendered["html"],
            "text": rendered["text"],
        }
    )


def send_password_reset_code_email(name, email, code):
    rendered = render_email_template("password_reset", {
        "name": name or "familia",
        "code": code,
    })

    return send_resend_email(
        {
            "to": email,
            "subject": rendered["subject"],
            "html": rendered["html"],
            "text": rendered["text"],
        }
    )


def send_welcome_email(to_email, name, store_url=None, account_url=None):
    rendered = render_email_template("welcome", {
        "name": name,
        "store_url": store_url or build_frontend_url("/tienda"),
        "account_url": account_url or build_frontend_url("/perfil"),
    })
    return send_resend_email({
        "to": to_email,
        "subject": rendered["subject"],
        "html": rendered["html"],
        "text": rendered["text"],
    })


def send_download_ready_email(to_email, name, product_title, library_url=None, file_type="", support_url=None):
    rendered = render_email_template("download_ready", {
        "name": name,
        "product_title": product_title,
        "library_url": library_url or build_frontend_url("/perfil#biblioteca"),
        "file_type": file_type,
        "support_url": support_url or "contacto@paolapsicope.com",
    })
    return send_resend_email({
        "to": to_email,
        "subject": rendered["subject"],
        "html": rendered["html"],
        "text": rendered["text"],
    })


def send_download_help_email(to_email, name, library_url=None, support_email=None):
    rendered = render_email_template("download_help", {
        "name": name,
        "library_url": library_url or build_frontend_url("/perfil#biblioteca"),
        "support_email": support_email or "contacto@paolapsicope.com",
    })
    return send_resend_email({
        "to": to_email,
        "subject": rendered["subject"],
        "html": rendered["html"],
        "text": rendered["text"],
    })


def send_new_product_email(to_email, name, product_title, product_description="", product_price="", product_url=None):
    rendered = render_email_template("new_product", {
        "name": name,
        "product_title": product_title,
        "product_description": product_description,
        "product_price": product_price,
        "product_url": product_url or build_frontend_url("/tienda"),
    })
    return send_resend_email({
        "to": to_email,
        "subject": rendered["subject"],
        "html": rendered["html"],
        "text": rendered["text"],
    })


def send_product_updated_email(to_email, name, product_title, changes=None, product_url=None):
    rendered = render_email_template("product_updated", {
        "name": name,
        "product_title": product_title,
        "changes": changes or [],
        "product_url": product_url or build_frontend_url("/tienda"),
    })
    return send_resend_email({
        "to": to_email,
        "subject": rendered["subject"],
        "html": rendered["html"],
        "text": rendered["text"],
    })


def send_abandoned_cart_email(to_email, name, product_title, product_price="", cart_url=None):
    rendered = render_email_template("abandoned_cart", {
        "name": name,
        "product_title": product_title,
        "product_price": product_price,
        "cart_url": cart_url or build_frontend_url("/carrito"),
    })
    return send_resend_email({
        "to": to_email,
        "subject": rendered["subject"],
        "html": rendered["html"],
        "text": rendered["text"],
    })


def send_support_received_email(to_email, name, ticket_subject=None, support_email=None):
    rendered = render_email_template("support_received", {
        "name": name,
        "ticket_subject": ticket_subject or "",
        "support_email": support_email or "contacto@paolapsicope.com",
    })
    return send_resend_email({
        "to": to_email,
        "subject": rendered["subject"],
        "html": rendered["html"],
        "text": rendered["text"],
    })
