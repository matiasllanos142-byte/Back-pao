from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Order, User


@override_settings(
    ADMIN_USERNAME="paola-admin",
    ADMIN_PASSWORD_HASH=make_password("secreto-admin"),
    ADMIN_JWT_SECRET="test-admin-secret-with-at-least-32-bytes",
    ADMIN_TOKEN_TTL=3600,
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
)
class DashboardStatsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(
            username="buyer@example.com",
            email="buyer@example.com",
            first_name="Buyer",
            password=make_password("password"),
            email_verified=True,
            email_verified_at=timezone.now(),
        )

    def _admin_headers(self):
        login = self.client.post(
            "/api/admin/login",
            {"username": "paola-admin", "password": "secreto-admin"},
            format="json",
        )
        return {"HTTP_AUTHORIZATION": f"Bearer {login.data['accessToken']}"}

    def _order(self, status):
        return Order.objects.create(
            user=self.user,
            total="1000.00",
            status=status,
            customer_name="Buyer",
            customer_email=self.user.email,
        )

    def test_purchases_only_count_completed_orders(self):
        self._order("completada")
        self._order("completada")
        self._order("pendiente")
        self._order("fallida")

        response = self.client.get("/api/admin/dashboard/stats", **self._admin_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["orders"], 4)
        self.assertEqual(response.data["summary"]["purchases"], 2)
        self.assertEqual(response.data["summary"]["completedOrders"], 2)
        self.assertEqual(response.data["summary"]["pendingOrders"], 1)
        self.assertEqual(response.data["summary"]["failedOrders"], 1)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("generatedAt", response.data)
