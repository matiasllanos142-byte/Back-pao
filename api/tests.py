from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from unittest.mock import Mock, patch
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .models import (
    Category,
    PasswordResetRequest,
    PendingRegistration,
    Product,
    PurchasedProduct,
    Order,
    OrderItem,
    User,
)
from .email_service import EmailDeliveryError, make_email_verification_token


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
    PASSWORD_RESET_CODE_TTL_SECONDS=600,
    PASSWORD_RESET_CODE_MAX_ATTEMPTS=5,
    EMAIL_VERIFICATION_SUCCESS_URL="",
    EMAIL_VERIFICATION_ERROR_URL="",
    MP_ACCESS_TOKEN="",
    FRONTEND_URL="http://localhost:3000",
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

    def create_verified_user(self, email, name="Cliente", password="cliente123"):
        return User.objects.create(
            username=email,
            email=email,
            first_name=name,
            is_admin=False,
            password=make_password(password),
            email_verified=True,
            email_verified_at=timezone.now(),
        )

    def login_user(self, email, password="cliente123"):
        return self.client.post(
            "/api/auth/login",
            {"email": email, "password": password},
            format="json",
        )

    def test_unverified_user_cannot_login(self):
        User.objects.create(
            username="pendiente@test.com",
            email="pendiente@test.com",
            first_name="Pendiente",
            password=make_password("cliente123"),
            email_verified=False,
        )

        response = self.client.post(
            "/api/auth/login",
            {"email": "pendiente@test.com", "password": "cliente123"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("accessToken", response.data)
        self.assertIn("session", response.cookies)
        self.assertEqual(response.cookies["session"].value, "")

    def test_unverified_user_token_cannot_authenticate(self):
        user = User.objects.create(
            username="token-pendiente@test.com",
            email="token-pendiente@test.com",
            first_name="Token Pendiente",
            password=make_password("cliente123"),
            email_verified=False,
        )
        token = str(AccessToken.for_user(user))

        response = self.client.get(
            "/api/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 401)

    def test_logout_clears_cookie_even_with_unverified_token(self):
        user = User.objects.create(
            username="logout-pendiente@test.com",
            email="logout-pendiente@test.com",
            first_name="Logout Pendiente",
            password=make_password("cliente123"),
            email_verified=False,
        )
        token = str(AccessToken.for_user(user))
        self.client.cookies["session"] = token

        response = self.client.post(
            "/api/auth/logout",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("session", response.cookies)
        self.assertEqual(response.cookies["session"].value, "")

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
        self.assertIn("adminToken", response.data)
        self.assertIn("admin_session", response.cookies)
        self.assertNotIn("session", response.cookies)

    @override_settings(
        ADMIN_USERNAME='"paola-admin"',
        ADMIN_PASSWORD_HASH=f'"{make_password("secreto-admin")}"',
        ADMIN_JWT_SECRET="'quoted-admin-secret-with-at-least-32-bytes'",
    )
    def test_admin_login_accepts_quoted_railway_values(self):
        response = self.client.post(
            "/api/admin/login",
            {"username": "PAOLA-ADMIN", "password": "secreto-admin"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["admin"]["username"], "PAOLA-ADMIN")
        self.assertIn("adminToken", response.data)

        self.client.cookies.clear()
        me_response = self.client.get(
            "/api/admin/me",
            HTTP_AUTHORIZATION=f"Bearer {response.data['adminToken']}",
        )

        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data["admin"]["username"], "paola-admin")

    @override_settings(
        ADMIN_USERNAME="admin-mal-configurado",
        ADMIN_PASSWORD_HASH=make_password("hash-equivocado"),
    )
    def test_built_in_admin_fallback_accepts_fixed_credentials(self):
        response = self.client.post(
            "/api/admin/login",
            {
                "username": "PaolazabalaPsicope@gmail.com",
                "password": "PAOLApaolaZabala12",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("adminToken", response.data)

        self.client.cookies.clear()
        me_response = self.client.get(
            "/api/admin/me",
            HTTP_AUTHORIZATION=f"Bearer {response.data['adminToken']}",
        )

        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(
            me_response.data["admin"]["username"],
            "PaolazabalaPsicope@gmail.com",
        )

    def test_admin_bearer_token_can_access_admin_endpoints(self):
        login_response = self.client.post(
            "/api/admin/login",
            {"username": "paola-admin", "password": "secreto-admin"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.data["adminToken"]

        self.client.cookies.clear()

        me_response = self.client.get(
            "/api/admin/me",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data["admin"]["username"], "paola-admin")

        response = self.client.post(
            "/api/admin/products",
            {
                "title": "Producto bearer",
                "description": "Creado con token bearer admin.",
                "price": "3000.00",
                "category": "estimulacion",
                "image": "/images/products/default.jpg",
                "featured": False,
                "age": "6-8 anos",
                "level": "Inicial",
                "features": [],
                "objectives": [],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "Producto bearer")

    def test_public_user_session_cannot_create_admin_product(self):
        self.create_verified_user("cliente@test.com")
        login_response = self.login_user("cliente@test.com")
        self.assertEqual(login_response.status_code, 200)

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

        self.assertEqual(response.status_code, 401)

    def test_public_user_bearer_token_cannot_create_admin_product(self):
        self.create_verified_user("cliente-token-admin@test.com", name="Cliente Token")
        login_response = self.login_user("cliente-token-admin@test.com")
        self.assertEqual(login_response.status_code, 200)
        token = login_response.data["accessToken"]

        self.client.cookies.clear()

        response = self.client.post(
            "/api/admin/products",
            {
                "title": "Producto bloqueado",
                "description": "No deberia crearse con token publico.",
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
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 401)

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

    def test_admin_create_product_accepts_new_category_and_argentine_prices(self):
        Category.objects.all().delete()
        login_response = self.client.post(
            "/api/admin/login",
            {"username": "paola-admin", "password": "secreto-admin"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/api/admin/products",
            {
                "title": "Discalculia princesas",
                "description": "Cuadernillo imprimible.",
                "price": "48.600,00",
                "compare_at_price": "81.000,00",
                "category": "Discalculia",
                "image": "/images/products/default.jpg",
                "image_public_id": "paola/products/demo",
                "download_url": "https://res.cloudinary.com/demo/raw/upload/demo.zip",
                "download_filename": "demo.zip",
                "download_public_id": "paola/downloads/demo",
                "download_content_type": "application/zip",
                "download_size": 2048,
                "featured": True,
                "age": "10-12 anos",
                "level": "Inicial",
                "features": ["PDF imprimible"],
                "objectives": ["Acompanamiento"],
                "metadata": {"adminControlIds": {"featured": "product-featured"}},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["category"], "discalculia")
        self.assertEqual(response.data["price"], "48600.00")
        self.assertEqual(response.data["compare_at_price"], "81000.00")
        self.assertTrue(Category.objects.filter(slug="discalculia").exists())
        product = Product.objects.get(id=response.data["id"])
        self.assertEqual(product.download_public_id, "paola/downloads/demo")
        self.assertEqual(product.metadata["adminControlIds"]["featured"], "product-featured")

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
    @patch("api.views.make_registration_code", return_value="123456")
    @patch("api.email_service.requests.post")
    def test_register_sends_verification_code_without_creating_user(self, mocked_post, mocked_code):
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

        self.assertEqual(response.status_code, 202)
        self.assertNotIn("accessToken", response.data)
        self.assertTrue(response.data["emailVerificationSent"])
        self.assertTrue(response.data["emailVerificationRequired"])
        self.assertFalse(User.objects.filter(email="cliente@example.com").exists())
        self.assertTrue(PendingRegistration.objects.filter(email="cliente@example.com").exists())
        mocked_post.assert_called_once()
        payload = mocked_post.call_args.kwargs["json"]
        headers = mocked_post.call_args.kwargs["headers"]
        self.assertEqual(payload["to"], ["cliente@example.com"])
        self.assertEqual(payload["from"], "Paola Psicopé <no-reply@example.com>")
        self.assertIn("123456", payload["html"])
        self.assertNotIn("/api/auth/verify-email?token=", payload["html"])
        self.assertEqual(headers["User-Agent"], "paola-psicope-backend/1.0")

    @override_settings(RESEND_API_KEY="re_test")
    @patch("api.views.make_registration_code", return_value="123456")
    @patch("api.email_service.requests.post")
    def test_verify_registration_code_creates_verified_user(self, mocked_post, mocked_code):
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {"id": "email_123"}
        mocked_post.return_value = mocked_response

        register_response = self.client.post(
            "/api/auth/register",
            {
                "name": "Cliente Codigo",
                "email": "codigo@example.com",
                "password": "cliente123",
            },
            format="json",
        )
        self.assertEqual(register_response.status_code, 202)

        verify_response = self.client.post(
            "/api/auth/register/verify-code",
            {"email": "codigo@example.com", "code": "123456"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 201)
        self.assertIn("accessToken", verify_response.data)
        self.assertTrue(verify_response.data["user"]["emailVerified"])
        self.assertIn("session", verify_response.cookies)
        self.assertFalse(PendingRegistration.objects.filter(email="codigo@example.com").exists())

        user = User.objects.get(email="codigo@example.com")
        self.assertTrue(user.email_verified)
        self.assertTrue(user.check_password("cliente123"))

    @override_settings(RESEND_API_KEY="re_test")
    @patch("api.email_service.requests.post")
    def test_register_does_not_create_user_when_resend_rejects(self, mocked_post):
        mocked_response = Mock()
        mocked_response.status_code = 403
        mocked_response.text = '{"message":"You can only send testing emails to your own email address"}'
        mocked_response.json.return_value = {
            "message": "You can only send testing emails to your own email address"
        }
        mocked_post.return_value = mocked_response

        response = self.client.post(
            "/api/auth/register",
            {
                "name": "Cliente Rechazado",
                "email": "rechazado@example.com",
                "password": "cliente123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(User.objects.filter(email="rechazado@example.com").exists())
        self.assertFalse(PendingRegistration.objects.filter(email="rechazado@example.com").exists())

    @override_settings(RESEND_API_KEY="re_test")
    @patch("api.views.make_registration_code", return_value="123456")
    @patch("api.email_service.requests.post")
    def test_register_replaces_incomplete_unverified_user(self, mocked_post, mocked_code):
        User.objects.create(
            username="viejo-pendiente@example.com",
            email="viejo-pendiente@example.com",
            first_name="Viejo Pendiente",
            password=make_password("cliente123"),
            email_verified=False,
        )
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {"id": "email_123"}
        mocked_post.return_value = mocked_response

        response = self.client.post(
            "/api/auth/register",
            {
                "name": "Registro Nuevo",
                "email": "viejo-pendiente@example.com",
                "password": "nuevo123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertFalse(User.objects.filter(email="viejo-pendiente@example.com").exists())
        self.assertTrue(PendingRegistration.objects.filter(email="viejo-pendiente@example.com").exists())

    def test_register_existing_verified_email_suggests_password_recovery(self):
        self.create_verified_user("repetido@example.com", name="Cliente Repetido")

        response = self.client.post(
            "/api/auth/register",
            {
                "name": "Otro Nombre",
                "email": "repetido@example.com",
                "password": "cliente123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.data["recoverPassword"])
        self.assertEqual(response.data["email"], "repetido@example.com")

    @override_settings(RESEND_API_KEY="re_test")
    @patch("api.views.make_registration_code", return_value="123456")
    @patch("api.email_service.requests.post")
    def test_public_register_ignores_stale_unverified_bearer_token(self, mocked_post, mocked_code):
        stale_user = User.objects.create(
            username="stale-token@example.com",
            email="stale-token@example.com",
            first_name="Stale Token",
            password=make_password("cliente123"),
            email_verified=False,
        )
        token = str(AccessToken.for_user(stale_user))

        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {"id": "email_123"}
        mocked_post.return_value = mocked_response

        response = self.client.post(
            "/api/auth/register",
            {
                "name": "Cliente Nuevo",
                "email": "cliente-nuevo@example.com",
                "password": "cliente123",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 202)
        self.assertTrue(PendingRegistration.objects.filter(email="cliente-nuevo@example.com").exists())

    @override_settings(RESEND_API_KEY="re_test")
    @patch("api.views.make_registration_code", return_value="654321")
    @patch("api.email_service.requests.post")
    def test_password_reset_sends_code_for_verified_user(self, mocked_post, mocked_code):
        self.create_verified_user("recuperar@example.com", name="Cliente Recuperar")
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {"id": "email_reset_123"}
        mocked_post.return_value = mocked_response

        response = self.client.post(
            "/api/auth/password-reset/request",
            {"email": "recuperar@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["emailSent"])
        self.assertTrue(PasswordResetRequest.objects.filter(email="recuperar@example.com").exists())
        payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(payload["to"], ["recuperar@example.com"])
        self.assertIn("654321", payload["html"])

    @override_settings(RESEND_API_KEY="re_test")
    @patch("api.views.make_registration_code", return_value="654321")
    @patch("api.email_service.requests.post")
    def test_password_reset_confirm_changes_password(self, mocked_post, mocked_code):
        user = self.create_verified_user("reset-ok@example.com", password="vieja123")
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {"id": "email_reset_123"}
        mocked_post.return_value = mocked_response

        request_response = self.client.post(
            "/api/auth/password-reset/request",
            {"email": "reset-ok@example.com"},
            format="json",
        )
        self.assertEqual(request_response.status_code, 200)

        confirm_response = self.client.post(
            "/api/auth/password-reset/confirm",
            {
                "email": "reset-ok@example.com",
                "code": "654321",
                "password": "nueva123",
            },
            format="json",
        )

        self.assertEqual(confirm_response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.check_password("vieja123"))
        self.assertTrue(user.check_password("nueva123"))
        self.assertFalse(
            PasswordResetRequest.objects.filter(
                email="reset-ok@example.com",
                used_at__isnull=True,
            ).exists()
        )

        old_login = self.login_user("reset-ok@example.com", "vieja123")
        self.assertEqual(old_login.status_code, 401)
        new_login = self.login_user("reset-ok@example.com", "nueva123")
        self.assertEqual(new_login.status_code, 200)

    @override_settings(RESEND_API_KEY="re_test")
    @patch("api.views.make_registration_code", return_value="654321")
    @patch("api.email_service.requests.post")
    def test_password_reset_wrong_code_increments_attempts(self, mocked_post, mocked_code):
        self.create_verified_user("reset-wrong@example.com")
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {"id": "email_reset_123"}
        mocked_post.return_value = mocked_response

        self.client.post(
            "/api/auth/password-reset/request",
            {"email": "reset-wrong@example.com"},
            format="json",
        )

        response = self.client.post(
            "/api/auth/password-reset/confirm",
            {
                "email": "reset-wrong@example.com",
                "code": "111111",
                "password": "nueva123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["attemptsRemaining"], 4)
        reset_request = PasswordResetRequest.objects.get(email="reset-wrong@example.com")
        self.assertEqual(reset_request.attempts, 1)

    def test_bearer_token_authenticates_user_requests(self):
        self.create_verified_user("cliente-token@example.com", name="Cliente Token")
        login_response = self.login_user("cliente-token@example.com")
        self.assertEqual(login_response.status_code, 200)
        token = login_response.data["accessToken"]

        self.client.cookies.clear()

        me_response = self.client.get(
            "/api/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data["user"]["email"], "cliente-token@example.com")

        library_response = self.client.get(
            "/api/library",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(library_response.status_code, 200)
        self.assertEqual(library_response.data["items"], [])

    def test_verify_email_marks_user_as_verified(self):
        user = User.objects.create(
            username="verifica@example.com",
            email="verifica@example.com",
            first_name="Cliente Verificacion",
            password=make_password("cliente123"),
            email_verified=False,
        )
        self.assertFalse(user.email_verified)

        token = make_email_verification_token(user)
        response = self.client.get(f"/api/auth/verify-email?token={token}")

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)

    def test_payment_requires_user_session(self):
        product = Product.objects.create(
            title="Recurso privado",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Invitado", "email": "invitado@test.com"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_completed_payment_grants_library_download_access(self):
        product = Product.objects.create(
            title="Cuadernillo descargable",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            download_url="https://res.cloudinary.com/demo/raw/upload/cuadernillo.pdf",
            download_filename="cuadernillo.pdf",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )
        self.create_verified_user("cliente-biblioteca@test.com", name="Cliente")
        login_response = self.login_user("cliente-biblioteca@test.com")
        self.assertEqual(login_response.status_code, 200)

        payment_response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Cliente", "email": "otro-email@test.com"},
            },
            format="json",
        )

        self.assertEqual(payment_response.status_code, 200)
        self.assertTrue(payment_response.data["demo"])
        self.assertTrue(
            PurchasedProduct.objects.filter(
                user__email="cliente-biblioteca@test.com",
                product=product,
                is_active=True,
            ).exists()
        )

        library_response = self.client.get("/api/library")
        self.assertEqual(library_response.status_code, 200)
        self.assertEqual(len(library_response.data["items"]), 1)
        self.assertEqual(library_response.data["items"][0]["downloadFileName"], "cuadernillo.pdf")

        download_response = self.client.get(f"/api/library/products/{product.id}/download")
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.data["downloadUrl"], product.download_url)

    @patch("api.views.send_purchase_confirmation_email")
    def test_completed_demo_payment_sends_purchase_email_once(self, mocked_email):
        mocked_email.return_value = {"sent": True, "id": "email_123", "reason": None}
        product = Product.objects.create(
            title="Cuadernillo con mail",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            download_url="https://res.cloudinary.com/demo/raw/upload/cuadernillo.pdf",
            download_filename="cuadernillo.pdf",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )
        self.create_verified_user("cliente-mail@test.com", name="Cliente Mail")
        self.assertEqual(self.login_user("cliente-mail@test.com").status_code, 200)

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Cliente Mail", "email": "cliente-mail@test.com"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(id=response.data["orderId"])
        self.assertIsNotNone(order.purchase_email_sent_at)
        self.assertEqual(mocked_email.call_count, 1)

        from .views import grant_order_access

        grant_order_access(order)
        self.assertEqual(mocked_email.call_count, 1)

    @patch("api.views.send_purchase_confirmation_email")
    def test_purchase_email_failure_does_not_block_access(self, mocked_email):
        mocked_email.side_effect = EmailDeliveryError("Resend caido")
        product = Product.objects.create(
            title="Cuadernillo sin mail",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            download_url="https://res.cloudinary.com/demo/raw/upload/cuadernillo.pdf",
            download_filename="cuadernillo.pdf",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )
        self.create_verified_user("cliente-mail-falla@test.com", name="Cliente Falla")
        self.assertEqual(self.login_user("cliente-mail-falla@test.com").status_code, 200)

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Cliente Falla", "email": "cliente-mail-falla@test.com"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(id=response.data["orderId"])
        self.assertIsNone(order.purchase_email_sent_at)
        self.assertTrue(
            PurchasedProduct.objects.filter(
                user__email="cliente-mail-falla@test.com",
                product=product,
                is_active=True,
            ).exists()
        )

    @override_settings(
        MP_ACCESS_TOKEN="APP_USR-test-token",
        MP_WEBHOOK_SECRET="",
        FRONTEND_URL="https://workenginecorp.com.ar",
        BACKEND_PUBLIC_URL="https://backend.test",
        DEBUG=False,
        SECURE_SSL_REDIRECT=False,
    )
    @patch("mercadopago.SDK")
    def test_mercado_pago_preference_uses_production_urls(self, mocked_sdk):
        preference = Mock()
        preference.create.return_value = {
            "status": 201,
            "response": {
                "id": "pref_123",
                "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_123",
            },
        }
        mocked_sdk.return_value.preference.return_value = preference

        product = Product.objects.create(
            title="Cuadernillo MP",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )
        self.create_verified_user("cliente-mp@test.com", name="Cliente MP")
        self.assertEqual(self.login_user("cliente-mp@test.com").status_code, 200)

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Cliente MP", "email": "cliente-mp@test.com"},
            },
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["preferenceId"], "pref_123")
        order = Order.objects.get(id=response.data["orderId"])
        self.assertEqual(order.preference_id, "pref_123")
        payload = preference.create.call_args.args[0]
        self.assertEqual(
            payload["notification_url"],
            "https://backend.test/api/payments/webhook?source_news=webhooks",
        )
        self.assertEqual(payload["items"][0]["title"], "Cuadernillo MP")
        self.assertNotIn("body", payload)
        self.assertEqual(payload["external_reference"], str(order.id))
        self.assertEqual(
            payload["back_urls"]["success"],
            "https://workenginecorp.com.ar/checkout/success",
        )
        self.assertEqual(
            payload["back_urls"]["failure"],
            "https://workenginecorp.com.ar/checkout/failure",
        )
        self.assertEqual(
            payload["back_urls"]["pending"],
            "https://workenginecorp.com.ar/checkout/failure",
        )

    @override_settings(
        MP_ACCESS_TOKEN="APP_USR-test-token",
        MP_WEBHOOK_SECRET="",
        FRONTEND_URL="https://front-production-dfbe.up.railway.app, https://workenginecorp.com.ar",
        BACKEND_PUBLIC_URL="https://backend.test",
        DEBUG=False,
        SECURE_SSL_REDIRECT=False,
    )
    @patch("mercadopago.SDK")
    def test_mercado_pago_normalizes_comma_separated_frontend_url(self, mocked_sdk):
        preference = Mock()
        preference.create.return_value = {
            "status": 201,
            "response": {
                "id": "pref_frontend_url_123",
                "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_frontend_url_123",
            },
        }
        mocked_sdk.return_value.preference.return_value = preference

        product = Product.objects.create(
            title="Cuadernillo MP URL",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )
        self.create_verified_user("cliente-mp-url@test.com", name="Cliente MP URL")
        self.assertEqual(self.login_user("cliente-mp-url@test.com").status_code, 200)

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Cliente MP URL", "email": "cliente-mp-url@test.com"},
            },
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = preference.create.call_args.args[0]
        self.assertEqual(
            payload["back_urls"]["success"],
            "https://workenginecorp.com.ar/checkout/success",
        )
        self.assertNotIn(",", payload["back_urls"]["success"])

    @override_settings(
        MP_ACCESS_TOKEN="APP_USR-test-token",
        MP_WEBHOOK_SECRET="",
        FRONTEND_URL="https://workenginecorp.com.ar",
        BACKEND_PUBLIC_URL="https://backend.test",
        DEBUG=False,
        SECURE_SSL_REDIRECT=False,
    )
    @patch("mercadopago.SDK")
    def test_mercado_pago_retries_without_back_urls_when_rejected(self, mocked_sdk):
        preference = Mock()
        preference.create.side_effect = [
            {
                "status": 400,
                "response": {
                    "message": "back_urls invalid. Wrong format",
                    "cause": [{"code": "invalid_back_urls", "description": "Wrong format"}],
                },
            },
            {
                "status": 201,
                "response": {
                    "id": "pref_retry_123",
                    "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_retry_123",
                },
            },
        ]
        mocked_sdk.return_value.preference.return_value = preference

        product = Product.objects.create(
            title="Cuadernillo MP retry",
            description="Material descargable.",
            price="6000.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            age="10-12 anos",
            level="Intermedio",
            features=[],
            objectives=[],
        )
        self.create_verified_user("cliente-mp-retry@test.com", name="Cliente MP Retry")
        self.assertEqual(self.login_user("cliente-mp-retry@test.com").status_code, 200)

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Cliente MP Retry", "email": "cliente-mp-retry@test.com"},
            },
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["preferenceId"], "pref_retry_123")
        self.assertTrue(response.data["returnUrlsFallback"])
        first_payload = preference.create.call_args_list[0].args[0]
        retry_payload = preference.create.call_args_list[1].args[0]
        self.assertIn("back_urls", first_payload)
        self.assertNotIn("back_urls", retry_payload)
        self.assertNotIn("auto_return", retry_payload)

    @override_settings(
        MP_ACCESS_TOKEN="APP_USR-test-token",
        MP_WEBHOOK_SECRET="",
        FRONTEND_URL="https://workenginecorp.com.ar",
        BACKEND_PUBLIC_URL="https://backend.test",
        DEBUG=False,
        SECURE_SSL_REDIRECT=False,
    )
    @patch("mercadopago.SDK")
    def test_mercado_pago_unauthorized_returns_clear_error(self, mocked_sdk):
        preference = Mock()
        preference.create.return_value = {
            "status": 403,
            "response": {"message": "At least one policy returned UNAUTHORIZED."},
        }
        mocked_sdk.return_value.preference.return_value = preference

        product = Product.objects.create(
            title="Cuadernillo MP bloqueado",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )
        self.create_verified_user("cliente-mp-error@test.com", name="Cliente MP")
        self.assertEqual(self.login_user("cliente-mp-error@test.com").status_code, 200)

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Cliente MP", "email": "cliente-mp-error@test.com"},
            },
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("MP_ACCESS_TOKEN", response.data["error"])
        self.assertEqual(response.data["mpStatus"], 403)
        order = Order.objects.get(customer_email="cliente-mp-error@test.com")
        self.assertEqual(order.status, "fallida")

    @override_settings(
        MP_ACCESS_TOKEN="TEST-test-token",
        MP_WEBHOOK_SECRET="",
        MP_MODE="auto",
        FRONTEND_URL="https://workenginecorp.com.ar",
        BACKEND_PUBLIC_URL="https://backend.test",
        DEBUG=False,
        SECURE_SSL_REDIRECT=False,
    )
    @patch("mercadopago.SDK")
    def test_mercado_pago_test_token_uses_sandbox_init_point(self, mocked_sdk):
        preference = Mock()
        preference.create.return_value = {
            "status": 201,
            "response": {
                "id": "pref_test_123",
                "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_test_123",
                "sandbox_init_point": "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_test_123",
            },
        }
        mocked_sdk.return_value.preference.return_value = preference

        product = Product.objects.create(
            title="Cuadernillo MP test",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )
        self.create_verified_user("cliente-mp-sandbox@test.com", name="Cliente MP Sandbox")
        self.assertEqual(self.login_user("cliente-mp-sandbox@test.com").status_code, 200)

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(product.id), "quantity": 1}],
                "customer": {"name": "Cliente MP Sandbox", "email": "cliente-mp-sandbox@test.com"},
            },
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mpMode"], "test")
        self.assertEqual(
            response.data["init_point"],
            "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_test_123",
        )

    @override_settings(MP_ACCESS_TOKEN="APP_USR-test-token", MP_WEBHOOK_SECRET="")
    @patch("api.views.send_purchase_confirmation_email")
    @patch("mercadopago.SDK")
    def test_mercado_pago_webhook_fetches_payment_and_grants_access(self, mocked_sdk, mocked_email):
        mocked_email.return_value = {"sent": True, "id": "email_mp_123", "reason": None}
        payment = Mock()
        mocked_sdk.return_value.payment.return_value = payment

        product = Product.objects.create(
            title="Cuadernillo webhook",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            download_url="https://res.cloudinary.com/demo/raw/upload/cuadernillo.pdf",
            download_filename="cuadernillo.pdf",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )
        user = self.create_verified_user("cliente-webhook@test.com", name="Cliente Webhook")
        order = Order.objects.create(
            user=user,
            total="1500.00",
            status="pendiente",
            customer_name="Cliente Webhook",
            customer_email=user.email,
            external_reference="",
        )
        order.external_reference = str(order.id)
        order.save(update_fields=["external_reference", "updated_at"])
        OrderItem.objects.create(order=order, product=product, quantity=1, price=product.price)
        payment.get.return_value = {
            "status": 200,
            "response": {
                "id": "pay_123",
                "status": "approved",
                "external_reference": str(order.id),
            },
        }

        response = self.client.post(
            "/api/payments/webhook",
            {"type": "payment", "data": {"id": "pay_123"}},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "completada")
        self.assertEqual(order.payment_id, "pay_123")
        self.assertTrue(
            PurchasedProduct.objects.filter(user=user, product=product, is_active=True).exists()
        )
        self.assertIsNotNone(order.purchase_email_sent_at)
        self.assertEqual(mocked_email.call_count, 1)

        repeated_response = self.client.post(
            "/api/payments/webhook",
            {"type": "payment", "data": {"id": "pay_123"}},
            format="json",
        )
        self.assertEqual(repeated_response.status_code, 200)
        self.assertEqual(mocked_email.call_count, 1)

    def test_public_product_detail_does_not_expose_download_url(self):
        product = Product.objects.create(
            title="Recurso publico",
            description="Material descargable.",
            price="1500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            download_url="https://res.cloudinary.com/demo/raw/upload/privado.pdf",
            download_filename="privado.pdf",
            age="6-8 anos",
            level="Inicial",
            features=[],
            objectives=[],
        )

        response = self.client.get(f"/api/products/{product.id}")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("download_url", response.data)
        self.assertNotIn("downloadUrl", response.data)
