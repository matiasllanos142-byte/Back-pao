from io import BytesIO
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from .email_service import send_password_reset_code_email
from .models import (
    Category,
    Notification,
    Order,
    OrderItem,
    Payment,
    Product,
    PurchasedProduct,
    User,
    UserEvent,
    UserProfile,
)


def png_upload(name="avatar.png"):
    buffer = BytesIO()
    Image.new("RGB", (16, 16), color=(230, 120, 160)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class RefactorAuthAvatarAdminTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="cliente@example.com",
            email="cliente@example.com",
            password="Cliente123!",
            first_name="Cliente",
            email_verified=True,
        )

    def login(self):
        response = self.client.post(
            "/api/auth/login",
            {"email": self.user.email, "password": "Cliente123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response

    def test_me_and_login_expose_profile_contract(self):
        UserProfile.objects.create(
            user=self.user,
            avatar_url="https://cdn.example/avatar.png",
            avatar_public_id="private/public-id",
            phone="+54 9 11 0000 0000",
        )
        login = self.login()
        self.assertEqual(login.data["user"]["avatarUrl"], "https://cdn.example/avatar.png")
        self.assertNotIn("avatarPublicId", login.data["user"])

        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["phone"], "+54 9 11 0000 0000")
        self.assertIn("lastLoginAt", response.data["user"])

    def test_change_password_invalidates_previous_token(self):
        login = self.login()
        previous_token = login.data["accessToken"]
        response = self.client.patch(
            "/api/auth/change-password",
            {
                "currentPassword": "Cliente123!",
                "newPassword": "NuevaClave456!",
                "confirmPassword": "NuevaClave456!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        old_token_response = self.client.get(
            "/api/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {previous_token}",
        )
        self.assertEqual(old_token_response.status_code, 401)
        self.assertTrue(UserEvent.objects.filter(user=self.user, event_type="password_changed").exists())

        relogin = self.client.post(
            "/api/auth/login",
            {"email": self.user.email, "password": "NuevaClave456!"},
            format="json",
        )
        self.assertEqual(relogin.status_code, 200)

    @patch("api.views.get_cloudinary_credentials")
    @patch("api.views.requests.post")
    def test_avatar_upload_persists_public_id_but_does_not_expose_it(self, mocked_post, mocked_credentials):
        self.login()
        mocked_credentials.return_value = {
            "cloud_name": "demo",
            "api_key": "key",
            "api_secret": "secret",
        }
        mocked_response = Mock(status_code=200)
        mocked_response.json.return_value = {
            "secure_url": "https://cdn.example/new-avatar.png",
            "public_id": "paola-psicope/avatars/user/avatar",
        }
        mocked_post.return_value = mocked_response

        response = self.client.patch(
            "/api/auth/avatar",
            {"avatar": png_upload()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("avatarPublicId", response.data)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.avatar_public_id, "paola-psicope/avatars/user/avatar")
        self.assertTrue(UserEvent.objects.filter(user=self.user, event_type="avatar_updated").exists())

    @patch("api.views._cloudinary_delete_image", return_value=False)
    def test_avatar_delete_keeps_database_state_when_cloudinary_fails(self, _mocked_delete):
        self.login()
        profile = UserProfile.objects.create(
            user=self.user,
            avatar_url="https://cdn.example/avatar.png",
            avatar_public_id="avatars/original",
        )
        response = self.client.delete("/api/auth/avatar")
        self.assertEqual(response.status_code, 502)
        profile.refresh_from_db()
        self.assertEqual(profile.avatar_public_id, "avatars/original")

    def test_database_admin_can_read_user_feed(self):
        admin = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="Admin123!",
            is_admin=True,
            email_verified=True,
        )
        login = self.client.post(
            "/api/admin/login",
            {"username": admin.email, "password": "Admin123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        response = self.client.get("/api/admin/users?page=1&pageSize=20")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["pagination"]["totalItems"], 2)
        self.assertIn("emailsFailedCount", response.data["items"][0])

    @override_settings(RESEND_API_KEY="")
    def test_failed_transactional_email_is_recorded(self):
        result = send_password_reset_code_email("Cliente", self.user.email, "123456")
        self.assertFalse(result["sent"])
        notification = Notification.objects.get(recipient=self.user.email, type="password_reset")
        self.assertEqual(notification.status, "failed")
        self.assertTrue(UserEvent.objects.filter(user=self.user, event_type="email_failed").exists())


@override_settings(
    MP_ACCESS_TOKEN="APP_USR-test-token",
    MP_WEBHOOK_SECRET="",
    MP_ALLOW_UNSIGNED_WEBHOOKS_IN_DEBUG=True,
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
)
class RefactorPaymentTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(
            slug="tests",
            name="Tests",
            description="Tests",
            icon="Test",
            color="#000000",
        )
        self.product = Product.objects.create(
            title="Cuadernillo",
            description="Material",
            price="1500.00",
            category=self.category,
            image="/placeholder.png",
            download_url="https://cdn.example/material.pdf",
            download_filename="material.pdf",
            age="8-10",
            level="Intermedio",
            features=[],
            objectives=[],
        )
        self.user = User.objects.create_user(
            username="pago@example.com",
            email="pago@example.com",
            password="Cliente123!",
            first_name="Pago",
            email_verified=True,
        )
        self.order = Order.objects.create(
            user=self.user,
            total="1500.00",
            status="pendiente",
            customer_name="Pago",
            customer_email=self.user.email,
            preference_id="pref_123",
        )
        self.order.external_reference = str(self.order.id)
        self.order.save(update_fields=["external_reference"])
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            price=self.product.price,
        )

    def payment_payload(self, status_value):
        return {
            "id": "pay_123",
            "status": status_value,
            "status_detail": "accredited" if status_value == "approved" else "pending_waiting_payment",
            "external_reference": str(self.order.id),
            "transaction_amount": 1500.0,
            "currency_id": "ARS",
            "preference_id": "pref_123",
            "payer": {"email": self.user.email},
        }

    @patch("api.views.send_purchase_confirmation_email")
    @patch("mercadopago.SDK")
    def test_pending_payment_can_later_become_approved(self, mocked_sdk, mocked_email):
        payment_client = Mock()
        mocked_sdk.return_value.payment.return_value = payment_client
        payment_client.get.side_effect = [
            {"status": 200, "response": self.payment_payload("pending")},
            {"status": 200, "response": self.payment_payload("approved")},
        ]
        mocked_email.return_value = {"sent": True, "id": "email_123", "reason": None}

        first = self.client.post(
            "/api/payments/webhook",
            {"id": "event_pending", "action": "payment.updated", "data": {"id": "pay_123"}},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pendiente")

        second = self.client.post(
            "/api/payments/webhook",
            {"id": "event_approved", "action": "payment.updated", "data": {"id": "pay_123"}},
            format="json",
        )
        self.assertEqual(second.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "completada")
        self.assertEqual(Payment.objects.get(provider_payment_id="pay_123").status, "approved")
        self.assertTrue(PurchasedProduct.objects.filter(user=self.user, product=self.product).exists())

    @patch("api.views.send_purchase_confirmation_email")
    @patch("mercadopago.SDK")
    def test_duplicate_event_is_idempotent(self, mocked_sdk, mocked_email):
        payment_client = Mock()
        mocked_sdk.return_value.payment.return_value = payment_client
        payment_client.get.return_value = {"status": 200, "response": self.payment_payload("approved")}
        mocked_email.return_value = {"sent": True, "id": "email_123", "reason": None}
        payload = {"id": "event_same", "action": "payment.updated", "data": {"id": "pay_123"}}

        first = self.client.post("/api/payments/webhook", payload, format="json")
        second = self.client.post("/api/payments/webhook", payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["duplicate"])
        self.assertEqual(payment_client.get.call_count, 1)
        self.assertEqual(mocked_email.call_count, 1)

    @patch("mercadopago.SDK")
    def test_amount_mismatch_never_grants_access(self, mocked_sdk):
        payload = self.payment_payload("approved")
        payload["transaction_amount"] = 1.0
        payment_client = Mock()
        mocked_sdk.return_value.payment.return_value = payment_client
        payment_client.get.return_value = {"status": 200, "response": payload}

        response = self.client.post(
            "/api/payments/webhook",
            {"id": "event_bad_amount", "data": {"id": "pay_123"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ignored"], "amount_mismatch")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pendiente")
        self.assertFalse(PurchasedProduct.objects.filter(user=self.user).exists())

    @patch("mercadopago.SDK")
    def test_provider_lookup_failure_requests_retry(self, mocked_sdk):
        payment_client = Mock()
        mocked_sdk.return_value.payment.return_value = payment_client
        payment_client.get.return_value = {
            "status": 503,
            "response": {"message": "temporary error"},
        }
        response = self.client.post(
            "/api/payments/webhook",
            {"id": "event_retry", "data": {"id": "pay_123"}},
            format="json",
        )
        self.assertEqual(response.status_code, 503)

    @override_settings(DEBUG=False, MP_WEBHOOK_SECRET="")
    def test_unsigned_webhook_is_rejected_in_production(self):
        response = self.client.post(
            "/api/payments/webhook",
            {"id": "event_unsigned", "data": {"id": "pay_123"}},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_order_status_returns_payment_state_not_payment_identifier(self):
        Payment.objects.create(
            order=self.order,
            provider_payment_id="pay_123",
            preference_id="pref_123",
            status="pending",
            amount="1500.00",
            currency="ARS",
        )
        self.client.force_authenticate(self.user)
        response = self.client.get(f"/api/orders/{self.order.id}/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["paymentStatus"], "pending")
        self.assertFalse(response.data["libraryReady"])

