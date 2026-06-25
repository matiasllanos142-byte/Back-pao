from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Category


@override_settings(
    ADMIN_USERNAME="paola-admin",
    ADMIN_PASSWORD_HASH=make_password("secreto-admin"),
    ADMIN_JWT_SECRET="test-admin-secret-with-at-least-32-bytes",
    ADMIN_TOKEN_TTL=3600,
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    AUTH_COOKIE_SAMESITE="Lax",
    AUTH_COOKIE_SECURE=False,
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
