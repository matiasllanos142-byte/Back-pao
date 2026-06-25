from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import Mock, patch
from rest_framework.test import APIClient

from .models import Category, User
from .email_service import make_email_verification_token


@override_settings(
    ADMIN_USERNAME="paola-admin",
    ADMIN_PASSWORD_HASH=make_password("secreto-admin"),
    ADMIN_JWT_SECRET="test-admin-secret-with-at-least-32-bytes",
    ADMIN_TOKEN_TTL=3600,
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    AUTH_COOKIE_SAMESITE="Lax",
    AUTH_COOKIE_SECURE=False,
    CLOUDINARY_CLOUD_NAME="demo-cloud",
    CLOUDINARY_API_KEY="demo-key",
    CLOUDINARY_API_SECRET="demo-secret-with-at-least-32-bytes",
    CLOUDINARY_UPLOAD_FOLDER="tests/products",
    BACKEND_PUBLIC_URL="https://backend.test",
    RESEND_API_KEY="",
    RESEND_FROM_EMAIL="Paola Psicopé <no-reply@example.com>",
    RESEND_REPLY_TO="contacto@example.com",
    EMAIL_VERIFICATION_TOKEN_TTL_SECONDS=86400,
    EMAIL_VERIFICATION_SUCCESS_URL="",
    EMAIL_VERIFICATION_ERROR_URL="",
)
class AdminAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Category.objects.create(
            slug="estimulacion",
            name="Estimulacion Cognitiva",
            description="Recursos de estimulacion",
            icon="Brain",
            color="#3F87EC",
        )

    def test_admin_login_rejects_invalid_credentials(self):
        response = self.client.post(
            "/api/admin/login",
            {"username": "paola-admin", "password": "incorrecto"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("admin_session", response.cookies)

    def test_admin_login_sets_separate_cookie(self):
        response = self.client.post(
            "/api/admin/login",
            {"username": "paola-admin", "password": "secreto-admin"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["admin"]["username"], "paola-admin")
        self.assertIn("admin_session", response.cookies)
        self.assertNotIn("session", response.cookies)

    def test_public_user_session_cannot_create_admin_product(self):
        register_response = self.client.post(
            "/api/auth/register",
            {"name": "Cliente", "email": "cliente@test.com", "password": "cliente123"},
            format="json",
        )
        self.assertEqual(register_response.status_code, 201)

        response = self.client.post(
            "/api/admin/products",
            {
                "title": "Producto privado",
                "description": "No deberia crearse con sesion publica.",
                "price": "1000.00",
                "category": "estimulacion",
                "image": "/images/products/default.jpg",
                "featured": False,
                "age": "6-8 anos",
                "level": "Inicial",
                "features": [],
                "objectives": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_cookie_can_create_product(self):
        login_response = self.client.post(
            "/api/admin/login",
            {"username": "paola-admin", "password": "secreto-admin"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/api/admin/products",
            {
                "title": "Cuadernillo inicial",
                "description": "Material descargable.",
                "price": "2500.00",
                "category": "estimulacion",
                "image": "/images/products/default.jpg",
                "featured": True,
                "age": "6-8 anos",
                "level": "Inicial",
                "features": ["PDF imprimible"],
                "objectives": ["Acompanamiento"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "Cuadernillo inicial")

    @patch("api.views.requests.post")
    def test_admin_cookie_can_upload_image_to_cloudinary(self, mocked_post):
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {
            "secure_url": "https://res.cloudinary.com/demo/image/upload/sample.jpg",
            "public_id": "tests/products/sample",
        }
        mocked_post.return_value = mocked_response

        login_response = self.client.post(
            "/api/admin/login",
            {"username": "paola-admin", "password": "secreto-admin"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)

        image = SimpleUploadedFile(
            "producto.png",
            b"fake-image-content",
            content_type="image/png",
        )
        response = self.client.post(
            "/api/admin/uploads/image",
            {"image": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["url"], "https://res.cloudinary.com/demo/image/upload/sample.jpg")
        self.assertEqual(response.data["publicId"], "tests/products/sample")
        mocked_post.assert_called_once()

    @override_settings(RESEND_API_KEY="re_test")
    @patch("api.email_service.requests.post")
    def test_register_sends_verification_email_with_resend(self, mocked_post):
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {"id": "email_123"}
        mocked_post.return_value = mocked_response

        response = self.client.post(
            "/api/auth/register",
            {
                "name": "Paola Cliente",
                "email": "cliente@example.com",
                "password": "cliente123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["emailVerificationSent"])
        self.assertFalse(response.data["user"]["emailVerified"])
        mocked_post.assert_called_once()
        payload = mocked_post.call_args.kwargs["json"]
        headers = mocked_post.call_args.kwargs["headers"]
        self.assertEqual(payload["to"], ["cliente@example.com"])
        self.assertEqual(payload["from"], "Paola Psicopé <no-reply@example.com>")
        self.assertIn("https://backend.test/api/auth/verify-email?token=", payload["html"])
        self.assertEqual(headers["User-Agent"], "paola-psicope-backend/1.0")

    def test_verify_email_marks_user_as_verified(self):
        register_response = self.client.post(
            "/api/auth/register",
            {
                "name": "Cliente Verificacion",
                "email": "verifica@example.com",
                "password": "cliente123",
            },
            format="json",
        )
        self.assertEqual(register_response.status_code, 201)

        user = User.objects.get(email="verifica@example.com")
        self.assertFalse(user.email_verified)

        token = make_email_verification_token(user)
        response = self.client.get(f"/api/auth/verify-email?token={token}")

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)
