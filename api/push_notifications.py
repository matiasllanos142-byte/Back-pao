import base64
import json
import logging
import os

from django.utils import timezone

from .models import Notification, PushDevice

logger = logging.getLogger(__name__)


def _service_account_data():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    encoded = os.environ.get("FIREBASE_SERVICE_ACCOUNT_BASE64", "").strip()
    if encoded and not raw:
        raw = base64.b64decode(encoded).decode("utf-8")
    if not raw:
        return None
    data = json.loads(raw)
    private_key = data.get("private_key")
    if isinstance(private_key, str):
        data["private_key"] = private_key.replace("\\n", "\n")
    return data


def _firebase_app():
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app()
    except ValueError:
        account = _service_account_data()
        if account:
            return firebase_admin.initialize_app(credentials.Certificate(account))
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            return firebase_admin.initialize_app()
        return None


def firebase_is_configured():
    return bool(
        os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        or os.environ.get("FIREBASE_SERVICE_ACCOUNT_BASE64")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )


def send_push_to_user(user, *, title, body, data=None, notification_type="manual_push", order=None):
    tokens = list(
        PushDevice.objects.filter(user=user, active=True).values_list("token", flat=True)
    )
    notification = Notification.objects.create(
        user=user,
        order=order,
        type=notification_type,
        channel="push",
        recipient=user.email,
        status="pending",
        metadata={"title": title, "body": body, "targetCount": len(tokens), "data": data or {}},
    )
    if not tokens:
        notification.status = "failed"
        notification.failed_at = timezone.now()
        notification.error_message = "No hay dispositivos activos registrados."
        notification.save(update_fields=["status", "failed_at", "error_message", "updated_at"])
        return {"sent": 0, "failed": 0, "reason": "no_devices", "notification": notification}

    try:
        from firebase_admin import messaging

        app = _firebase_app()
        if app is None:
            raise RuntimeError("Firebase no esta configurado en el servidor.")

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={str(key): str(value) for key, value in (data or {}).items()},
            tokens=tokens,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(channel_id="paola_updates"),
            ),
        )
        response = messaging.send_each_for_multicast(message, app=app)

        invalid_tokens = []
        message_ids = []
        for token, result in zip(tokens, response.responses):
            if result.success:
                if result.message_id:
                    message_ids.append(result.message_id)
                continue
            error = str(result.exception or "")
            if "registration-token-not-registered" in error or "not found" in error.lower():
                invalid_tokens.append(token)

        if invalid_tokens:
            PushDevice.objects.filter(token__in=invalid_tokens).update(active=False)

        notification.attempts = 1
        notification.provider_message_id = ",".join(message_ids)[:300]
        notification.metadata = {
            **notification.metadata,
            "successCount": response.success_count,
            "failureCount": response.failure_count,
        }
        if response.success_count:
            notification.status = "sent"
            notification.sent_at = timezone.now()
        else:
            notification.status = "failed"
            notification.failed_at = timezone.now()
            notification.error_message = "Firebase rechazo todos los destinatarios."
        notification.save()
        return {
            "sent": response.success_count,
            "failed": response.failure_count,
            "notification": notification,
        }
    except Exception as exc:
        logger.exception("No se pudo enviar push al usuario %s", user.id)
        notification.attempts = 1
        notification.status = "failed"
        notification.failed_at = timezone.now()
        notification.error_message = str(exc)[:1000]
        notification.save()
        return {"sent": 0, "failed": len(tokens), "reason": str(exc), "notification": notification}
