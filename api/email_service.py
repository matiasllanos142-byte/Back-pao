import logging
from urllib.parse import urlparse

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
    library_url = build_frontend_url("/perfil#biblioteca")
    app_url = build_frontend_url("/#app")
    safe_name = escape(order.customer_name or "familia")
    safe_library_url = escape(library_url)
    safe_app_url = escape(app_url)
    safe_total = escape(f"$ {order.total}")

    items = list(order.items.select_related("product"))
    product_rows = []
    product_lines = []
    for item in items:
        title = escape(item.product.title)
        quantity = escape(str(item.quantity))
        line_total = escape(f"$ {item.price * item.quantity}")
        product_rows.append(
            f"""
            <tr>
              <td style="padding:12px 0;border-bottom:1px solid #E7E2EA">
                <p style="margin:0;font-size:15px;font-weight:700;color:#111111">{title}</p>
                <p style="margin:4px 0 0;font-size:13px;color:#5F5F68">Cantidad: {quantity}</p>
              </td>
              <td style="padding:12px 0;border-bottom:1px solid #E7E2EA;text-align:right;font-size:15px;font-weight:700;color:#111111">
                {line_total}
              </td>
            </tr>
            """
        )
        product_lines.append(f"- {item.product.title} x {item.quantity}: $ {item.price * item.quantity}")

    products_html = "".join(product_rows) or """
      <tr>
        <td style="padding:12px 0;color:#5F5F68">Tu material comprado ya esta disponible.</td>
        <td></td>
      </tr>
    """
    products_text = "\n".join(product_lines) or "- Material comprado disponible en tu biblioteca"

    subject = "Gracias por tu compra en Paola Psicope"
    html = f"""
    <div style="margin:0;padding:0;background:#FAF7FB;font-family:Arial,sans-serif;color:#111111">
      <div style="max-width:680px;margin:0 auto;padding:34px 16px">
        <div style="background:#ffffff;border:1px solid #E7E2EA;border-radius:24px;overflow:hidden;box-shadow:0 18px 50px rgba(30,20,40,.08)">
          <div style="padding:30px 30px 20px;background:#FAF7FB;border-bottom:1px solid #E7E2EA">
            <p style="margin:0 0 10px;font-size:12px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:#3B82F6">
              Paola Psicop&eacute; · Biblioteca
            </p>
            <h1 style="margin:0;font-size:30px;line-height:1.15;color:#111111">
              Gracias por tu compra
            </h1>
          </div>

          <div style="padding:30px;line-height:1.65">
            <p style="margin:0 0 14px;font-size:16px">Hola {safe_name},</p>
            <p style="margin:0 0 18px;font-size:16px;color:#333333">
              El material quedo guardado en tu cuenta para que puedas descargarlo cuando lo necesites.
            </p>

            <div style="background:#F7D7F2;border-radius:18px;padding:18px 20px;margin:0 0 22px">
              <p style="margin:0;font-size:14px;color:#4b2445">
                Tu compra ya esta aprobada. Entrando a tu perfil vas directo a la biblioteca de recursos.
              </p>
            </div>

            <table role="presentation" style="width:100%;border-collapse:collapse;margin:0 0 22px">
              <tbody>
                {products_html}
                <tr>
                  <td style="padding:16px 0 0;font-size:16px;font-weight:800;color:#111111">Total</td>
                  <td style="padding:16px 0 0;text-align:right;font-size:18px;font-weight:800;color:#3B82F6">{safe_total}</td>
                </tr>
              </tbody>
            </table>

            <p style="margin:0 0 18px">
              <a href="{safe_library_url}" style="display:inline-block;background:#3B82F6;color:#ffffff;text-decoration:none;padding:14px 22px;border-radius:999px;font-weight:800">
                Ver mis compras
              </a>
              <a href="{safe_app_url}" style="display:inline-block;margin-left:10px;color:#111111;text-decoration:none;padding:13px 20px;border:1px solid #E7E2EA;border-radius:999px;font-weight:700">
                Abrir la app
              </a>
            </p>

            <p style="margin:0;font-size:13px;color:#5F5F68">
              Por seguridad no adjuntamos archivos en este email. La descarga se realiza desde tu cuenta.
            </p>
          </div>

          <div style="padding:18px 30px;background:#FAF7FB;border-top:1px solid #E7E2EA">
            <p style="margin:0;font-size:13px;color:#5F5F68">
              Paola Psicope · Recursos psicopedagogicos · @paola_psicope
            </p>
          </div>
        </div>
      </div>
    </div>
    """
    text = (
        f"Hola {order.customer_name or ''},\n\n"
        "Gracias por tu compra en Paola Psicope.\n"
        "El material quedo guardado en tu cuenta para que puedas descargarlo cuando lo necesites.\n\n"
        f"Productos:\n{products_text}\n\n"
        f"Total: $ {order.total}\n\n"
        f"Ver mis compras: {library_url}\n"
        f"Abrir la app: {app_url}\n\n"
        "Por seguridad no adjuntamos archivos en este email. La descarga se realiza desde tu cuenta."
    )

    return send_resend_email(
        {
            "to": order.customer_email,
            "subject": subject,
            "html": html,
            "text": text,
        }
    )


def send_verification_email(user, request=None):
    verification_url = build_email_verification_url(user, request)
    safe_name = escape(user.first_name or "familia")
    safe_url = escape(verification_url)

    subject = "Confirma tu cuenta en Paola Psicope"
    html = f"""
    <div style="margin:0;padding:0;background:#f7f3f7;font-family:Arial,sans-serif;color:#111827">
      <div style="max-width:640px;margin:0 auto;padding:32px 16px">
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;overflow:hidden">
          <div style="background:#3F87EC;padding:26px 28px;color:#ffffff">
            <p style="margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase">
              Lic. Paola Zabala
            </p>
            <h1 style="margin:0;font-size:28px;line-height:1.2">
              Bienvenido/a a Paola Psicope
            </h1>
          </div>

          <div style="padding:28px;line-height:1.65">
            <p style="margin:0 0 14px;font-size:16px">Hola {safe_name},</p>
            <p style="margin:0 0 14px;font-size:16px">
              Gracias por crear tu cuenta en el espacio de Paola Psicope. Desde tu perfil vas a poder
              acceder a tus recursos comprados y acompanar tus procesos de aprendizaje con materiales
              organizados para familias, docentes y profesionales.
            </p>
            <p style="margin:0 0 22px;font-size:16px">
              Para confirmar que este email es real, toca el siguiente boton:
            </p>

            <p style="margin:0 0 24px">
              <a href="{safe_url}" style="display:inline-block;background:#3F87EC;color:#ffffff;text-decoration:none;padding:13px 20px;border-radius:999px;font-weight:700">
                Verificar mi email
              </a>
            </p>

            <div style="background:#f1f5f9;border-radius:14px;padding:16px 18px;margin:0 0 22px">
              <p style="margin:0;font-size:14px;color:#475569">
                Este enlace protege tu cuenta y permite asociar correctamente tus compras y descargas.
              </p>
            </div>

            <p style="margin:0 0 8px;font-size:14px;color:#6b7280">
              Si el boton no funciona, copia y pega este enlace en tu navegador:
            </p>
            <p style="margin:0 0 22px;word-break:break-all;font-size:13px;color:#3F87EC">
              {safe_url}
            </p>

            <p style="margin:0;font-size:14px;color:#6b7280">
              Si no creaste esta cuenta, podes ignorar este mensaje.
            </p>
          </div>

          <div style="padding:18px 28px;background:#fafafa;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-size:13px;color:#6b7280">
              Paola Psicope · Consultorio psicopedagogico · @paola_psicope
            </p>
          </div>
        </div>
      </div>
    </div>
    """
    text = (
        f"Hola {user.first_name or ''}, gracias por registrarte en Paola Psicope.\n\n"
        f"Confirma tu email abriendo este enlace:\n{verification_url}\n\n"
        "Desde tu perfil vas a poder acceder a tus recursos comprados.\n\n"
        "Si no creaste esta cuenta, podes ignorar este mensaje."
    )

    return send_resend_email(
        {
            "to": user.email,
            "subject": subject,
            "html": html,
            "text": text,
        }
    )


def send_registration_code_email(name, email, code):
    safe_name = escape(name or "familia")
    safe_code = escape(code)

    subject = f"Tu codigo de verificacion es {code}"
    html = f"""
    <div style="margin:0;padding:0;background:#f7f3f7;font-family:Arial,sans-serif;color:#111827">
      <div style="max-width:640px;margin:0 auto;padding:32px 16px">
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:22px;overflow:hidden">
          <div style="background:#3F87EC;padding:28px;color:#ffffff">
            <p style="margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase">
              Lic. Paola Zabala
            </p>
            <h1 style="margin:0;font-size:28px;line-height:1.2">
              Verifica tu cuenta
            </h1>
          </div>

          <div style="padding:30px;line-height:1.65">
            <p style="margin:0 0 14px;font-size:16px">Hola {safe_name},</p>
            <p style="margin:0 0 18px;font-size:16px">
              Para terminar de crear tu cuenta en Paola Psicope, ingresa este codigo en la pagina de registro:
            </p>

            <div style="margin:0 0 24px;text-align:center">
              <div style="display:inline-block;background:#eff6ff;border:1px solid #bfdbfe;border-radius:18px;padding:18px 26px">
                <p style="margin:0;color:#1d4ed8;font-size:34px;font-weight:800;letter-spacing:8px">
                  {safe_code}
                </p>
              </div>
            </div>

            <div style="background:#f8fafc;border-radius:14px;padding:16px 18px;margin:0 0 22px">
              <p style="margin:0;font-size:14px;color:#475569">
                Si no pediste crear esta cuenta, podes ignorar este email. No se creara ninguna cuenta sin este codigo.
              </p>
            </div>

            <p style="margin:0;font-size:14px;color:#6b7280">
              Este codigo vence en unos minutos para proteger tus datos.
            </p>
          </div>

          <div style="padding:18px 28px;background:#fafafa;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-size:13px;color:#6b7280">
              Paola Psicope · Consultorio psicopedagogico · @paola_psicope
            </p>
          </div>
        </div>
      </div>
    </div>
    """
    text = (
        f"Hola {name or ''},\n\n"
        f"Tu codigo para crear la cuenta en Paola Psicope es: {code}\n\n"
        "Si no pediste esta cuenta, ignora este mensaje."
    )

    return send_resend_email(
        {
            "to": email,
            "subject": subject,
            "html": html,
            "text": text,
        }
    )


def send_password_reset_code_email(name, email, code):
    safe_name = escape(name or "familia")
    safe_code = escape(code)

    subject = f"Tu codigo para recuperar la contrasena es {code}"
    html = f"""
    <div style="margin:0;padding:0;background:#f7f3f7;font-family:Arial,sans-serif;color:#111827">
      <div style="max-width:640px;margin:0 auto;padding:32px 16px">
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:22px;overflow:hidden">
          <div style="background:#3F87EC;padding:28px;color:#ffffff">
            <p style="margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase">
              Lic. Paola Zabala
            </p>
            <h1 style="margin:0;font-size:28px;line-height:1.2">
              Recupera tu acceso
            </h1>
          </div>

          <div style="padding:30px;line-height:1.65">
            <p style="margin:0 0 14px;font-size:16px">Hola {safe_name},</p>
            <p style="margin:0 0 18px;font-size:16px">
              Recibimos una solicitud para cambiar la contrasena de tu cuenta en Paola Psicope.
              Ingresa este codigo en la pagina de recuperacion:
            </p>

            <div style="margin:0 0 24px;text-align:center">
              <div style="display:inline-block;background:#eff6ff;border:1px solid #bfdbfe;border-radius:18px;padding:18px 26px">
                <p style="margin:0;color:#1d4ed8;font-size:34px;font-weight:800;letter-spacing:8px">
                  {safe_code}
                </p>
              </div>
            </div>

            <div style="background:#f8fafc;border-radius:14px;padding:16px 18px;margin:0 0 22px">
              <p style="margin:0;font-size:14px;color:#475569">
                Tu biblioteca y tus compras quedan asociadas a este email. La contrasena solo cambia si este codigo es correcto.
              </p>
            </div>

            <p style="margin:0 0 10px;font-size:14px;color:#6b7280">
              Si no pediste recuperar la cuenta, ignora este email. Nadie podra entrar sin el codigo.
            </p>
            <p style="margin:0;font-size:14px;color:#6b7280">
              Este codigo vence en unos minutos.
            </p>
          </div>

          <div style="padding:18px 28px;background:#fafafa;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-size:13px;color:#6b7280">
              Paola Psicope - Consultorio psicopedagogico - @paola_psicope
            </p>
          </div>
        </div>
      </div>
    </div>
    """
    text = (
        f"Hola {name or ''},\n\n"
        f"Tu codigo para recuperar la contrasena en Paola Psicope es: {code}\n\n"
        "Si no pediste recuperar la cuenta, ignora este mensaje."
    )

    return send_resend_email(
        {
            "to": email,
            "subject": subject,
            "html": html,
            "text": text,
        }
    )
