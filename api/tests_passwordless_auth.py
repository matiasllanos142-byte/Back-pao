from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import PendingRegistration


User = get_user_model()


@override_settings(
    EMAIL_ACCESS_CODE_RESEND_COOLDOWN_SECONDS=30,
    EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS=5,
)
class PasswordlessEmailAuthTests(APITestCase):
    @patch("api.views.send_access_code_email")
    @patch("api.views.make_registration_code", return_value="123456")
    def test_new_email_receives_code_and_creates_account_after_verification(
        self, mocked_code, mocked_send
    ):
        request_response = self.client.post(
            "/api/auth/email-code/request",
            {"email": "nueva.familia@example.com"},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertTrue(request_response.data["emailVerificationSent"])
        self.assertFalse(User.objects.filter(email="nueva.familia@example.com").exists())
        mocked_send.assert_called_once_with(
            "Nueva Familia", "nueva.familia@example.com", "123456"
        )

        verify_response = self.client.post(
            "/api/auth/email-code/verify",
            {"email": "nueva.familia@example.com", "code": "123456"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 201)
        self.assertTrue(verify_response.data["accountCreated"])
        self.assertIn("accessToken", verify_response.data)
        self.assertIn("session", verify_response.cookies)

        user = User.objects.get(email="nueva.familia@example.com")
        self.assertTrue(user.email_verified)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(
            PendingRegistration.objects.filter(email="nueva.familia@example.com").exists()
        )

    @patch("api.views.send_access_code_email")
    @patch("api.views.make_registration_code", return_value="654321")
    def test_existing_account_logs_in_without_creating_duplicate(
        self, mocked_code, mocked_send
    ):
        user = User.objects.create_user(
            username="existente@example.com",
            email="existente@example.com",
            first_name="Cuenta Existente",
            password="clave-anterior",
            email_verified=True,
        )

        self.client.post(
            "/api/auth/email-code/request",
            {"email": "existente@example.com"},
            format="json",
        )
        verify_response = self.client.post(
            "/api/auth/email-code/verify",
            {"email": "existente@example.com", "code": "654321"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertFalse(verify_response.data["accountCreated"])
        self.assertEqual(
            verify_response.data["user"]["id"],
            str(user.id),
        )
        self.assertEqual(User.objects.filter(email="existente@example.com").count(), 1)
        mocked_send.assert_called_once_with(
            "Cuenta Existente", "existente@example.com", "654321"
        )

    @patch("api.views.send_access_code_email")
    @patch("api.views.make_registration_code", return_value="123456")
    def test_wrong_code_reports_remaining_attempts(self, mocked_code, mocked_send):
        self.client.post(
            "/api/auth/email-code/request",
            {"email": "intentos@example.com"},
            format="json",
        )

        response = self.client.post(
            "/api/auth/email-code/verify",
            {"email": "intentos@example.com", "code": "000000"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["attemptsRemaining"], 4)
        self.assertEqual(
            PendingRegistration.objects.get(email="intentos@example.com").attempts,
            1,
        )

    @patch("api.views.send_access_code_email")
    @patch("api.views.make_registration_code", return_value="123456")
    def test_request_rate_limits_immediate_resend(self, mocked_code, mocked_send):
        first_response = self.client.post(
            "/api/auth/email-code/request",
            {"email": "reenvio@example.com"},
            format="json",
        )
        second_response = self.client.post(
            "/api/auth/email-code/request",
            {"email": "reenvio@example.com"},
            format="json",
        )

        self.assertEqual(first_response.status_code, 202)
        self.assertEqual(second_response.status_code, 429)
        self.assertGreater(second_response.data["retryAfterSeconds"], 0)
        mocked_send.assert_called_once()

    def test_request_rejects_invalid_email(self):
        response = self.client.post(
            "/api/auth/email-code/request",
            {"email": "no-es-un-email"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Ingresa un email valido.")
