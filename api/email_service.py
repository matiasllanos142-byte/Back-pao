import logging
from urllib.parse import quote, urlparse

import requests
from django.conf import settings
from django.core import signing
from django.utils import timezone
from django.utils.html import escape

from .email_templates import render_email_template

logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_SALT = "paola-psicope.email-verification"
GUEST_ORDER_SALT = "paola-psicope.guest-order"


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


def make_guest_order_token(order):
    return signing.dumps(
        {"order_id": str(order.id), "email": order.customer_email.lower()},
        salt=GUEST_ORDER_SALT,
    )


def read_guest_order_token(token):
    return signing.loads(
        token,
        salt=GUEST_ORDER_SALT,
        max_age=getattr(settings, "GUEST_ORDER_TOKEN_TTL_SECONDS", 60 * 60 * 24 * 30),
    )


def build_guest_download_url(order, product):
    token = quote(make_guest_order_token(order), safe="")
    path = f"/api/orders/{order.id}/downloads/{product.id}?token={token}"
    if settings.BACKEND_PUBLIC_URL:
        return f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}{path}"
    return path


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


def _email_notification(message):
    existing = message.get("notification")
    if existing is not None:
        return existing

    from .models import Notification, User, UserEvent

    recipient = str(message["to"]).lower().strip()
    user = message.get("user") or User.objects.filter(email__iexact=recipient).first()
    notification = Notification.objects.create(
        user=user,
        order=message.get("order"),
        type=message.get("notificationType", "transactional_email"),
        channel="email",
        recipient=recipient,
        status="pending",
        metadata=message.get("notificationMetadata") or {},
    )
    if user:
        UserEvent.objects.create(
            user=user,
            event_type="email_queued",
            entity_type="notification",
            entity_id=str(notification.id),
        )
    return notification


def _email_notification_sent(notification, provider_id):
    from .models import UserEvent

    notification.status = "sent"
    notification.provider_message_id = str(provider_id or "")
    notification.sent_at = timezone.now()
    notification.failed_at = None
    notification.error_message = ""
    notification.attempts += 1
    notification.save(update_fields=[
        "status", "provider_message_id", "sent_at", "failed_at",
        "error_message", "attempts", "updated_at",
    ])
    if notification.user:
        UserEvent.objects.create(
            user=notification.user,
            event_type="email_sent",
            entity_type="notification",
            entity_id=str(notification.id),
        )


def _email_notification_failed(notification, reason):
    from .models import UserEvent

    notification.status = "failed"
    notification.failed_at = timezone.now()
    notification.error_message = str(reason or "unknown_error")[:500]
    notification.attempts += 1
    notification.save(update_fields=[
        "status", "failed_at", "error_message", "attempts", "updated_at",
    ])
    if notification.user:
        UserEvent.objects.create(
            user=notification.user,
            event_type="email_failed",
            entity_type="notification",
            entity_id=str(notification.id),
        )


def send_resend_email(message):
    notification = _email_notification(message)
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY is not configured; email was not sent.")
        _email_notification_failed(notification, "missing_api_key")
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
        _email_notification_failed(notification, "resend_unreachable")
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
        _email_notification_failed(notification, reason)
        raise EmailDeliveryError(reason)

    try:
        data = response.json()
    except ValueError as exc:
        _email_notification_failed(notification, "invalid_resend_response")
        raise EmailDeliveryError("Resend devolvio una respuesta invalida.") from exc
    _email_notification_sent(notification, data.get("id"))
    return {"sent": True, "id": data.get("id"), "reason": None}


def send_purchase_confirmation_email(order, notification=None):
    items = list(order.items.select_related("product"))
    first_product = items[0].product.title if items else "Material comprado"
    is_guest = not order.user_id
    download_links = [
        {
            "label": item.product.download_filename or item.product.title,
            "url": build_guest_download_url(order, item.product),
        }
        for item in items
        if is_guest and item.product.download_url
    ]
    order_url = download_links[0]["url"] if download_links else build_frontend_url("/perfil#biblioteca")

    rendered = render_email_template("purchase_confirmed", {
        "name": order.customer_name or "familia",
        "order_id": f"#{str(order.id)[:8]}",
        "product_title": first_product,
        "total": f"$ {order.total}",
        "payment_status": "Aprobado",
        "order_url": order_url,
        "download_links": download_links,
        "guest_checkout": is_guest,
    })

    return send_resend_email(
        {
            "to": order.customer_email,
            "subject": rendered["subject"],
            "html": rendered["html"],
            "text": rendered["text"],
            "notificationType": "purchase_confirmed",
            "user": order.user,
            "order": order,
            "notification": notification,
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
            "notificationType": "verify_account",
            "user": user,
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
            "notificationType": "verify_account",
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
            "notificationType": "password_reset",
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
        "notificationType": "welcome",
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
        "notificationType": "download_ready",
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
        "notificationType": "download_help",
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
        "notificationType": "new_product",
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
        "notificationType": "product_updated",
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
        "notificationType": "abandoned_cart",
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
        "notificationType": "support_received",
    })
