import logging

import requests
from django.conf import settings
from django.core import signing
from django.utils.html import escape

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


def send_resend_email(message):
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY is not configured; email was not sent.")
        return {"sent": False, "id": None}

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
        raise EmailDeliveryError("Resend rechazo el envio del email.")

    data = response.json()
    return {"sent": True, "id": data.get("id")}


def send_verification_email(user, request=None):
    verification_url = build_email_verification_url(user, request)
    safe_name = escape(user.first_name or "Paola Psicopé")
    safe_url = escape(verification_url)

    subject = "Confirmá tu cuenta en Paola Psicopé"
    html = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#1f2937">
      <h1 style="font-size:22px;color:#111827">Confirmá tu cuenta</h1>
      <p>Hola {safe_name}, gracias por registrarte en Paola Psicopé.</p>
      <p>Para confirmar que este email es real, hacé click en el siguiente botón:</p>
      <p>
        <a href="{safe_url}" style="display:inline-block;background:#3F87EC;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:999px;font-weight:700">
          Verificar email
        </a>
      </p>
      <p>Si el botón no funciona, copiá y pegá este enlace en tu navegador:</p>
      <p style="word-break:break-all;color:#4b5563">{safe_url}</p>
      <p>Si no creaste esta cuenta, podés ignorar este mensaje.</p>
    </div>
    """
    text = (
        f"Hola {user.first_name or ''}, gracias por registrarte en Paola Psicopé.\n\n"
        f"Confirmá tu email abriendo este enlace:\n{verification_url}\n\n"
        "Si no creaste esta cuenta, podés ignorar este mensaje."
    )

    return send_resend_email(
        {
            "to": user.email,
            "subject": subject,
            "html": html,
            "text": text,
        }
    )
