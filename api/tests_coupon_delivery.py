from unittest.mock import Mock, patch

from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .email_service import make_checkout_return_token
from .models import Category, Coupon, Order, OrderItem, Payment, Product, User


@override_settings(
    ADMIN_USERNAME="paola-admin",
    ADMIN_PASSWORD_HASH=make_password("secreto-admin"),
    ADMIN_JWT_SECRET="test-admin-secret-with-at-least-32-bytes",
    ADMIN_TOKEN_TTL=3600,
    FRONTEND_URL="https://frontend.test",
    BACKEND_PUBLIC_URL="https://backend.test",
    MP_MODE="production",
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
)
class CouponDeliveryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Category.objects.create(
            slug="diagnostico",
            name="Diagnostico",
            description="Recursos de prueba.",
            icon="Book",
            color="#7C3AED",
        )
        self.product = Product.objects.create(
            title="Cuadernillo de prueba",
            description="Material descargable.",
            price="1000.00",
            category_id="diagnostico",
            product_type="product",
            image="/test.jpg",
            download_url="https://files.test/cuadernillo.pdf",
            download_filename="cuadernillo.pdf",
            age="6-8",
            level="Inicial",
            features=[],
            objectives=[],
        )

    def checkout_payload(self, code):
        return {
            "items": [{"productId": str(self.product.id), "quantity": 1}],
            "customer": {
                "name": "Familia Test",
                "email": "familia@example.com",
                "phone": "1123456789",
            },
            "promoCode": code,
        }

    def admin_headers(self):
        login = self.client.post(
            "/api/admin/login",
            {"username": "paola-admin", "password": "secreto-admin"},
            format="json",
        )
        return {"HTTP_AUTHORIZATION": f"Bearer {login.data['accessToken']}"}

    def test_admin_can_create_list_and_pause_coupon(self):
        headers = self.admin_headers()
        created = self.client.post(
            "/api/admin/coupons",
            {
                "code": " paola100 ",
                "discount_percent": 100,
                "max_uses": 3,
                "is_active": True,
            },
            format="json",
            **headers,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["coupon"]["code"], "PAOLA100")

        listed = self.client.get("/api/admin/coupons", **headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data["coupons"]), 1)

        coupon_id = created.data["coupon"]["id"]
        paused = self.client.patch(
            f"/api/admin/coupons/{coupon_id}",
            {"is_active": False},
            format="json",
            **headers,
        )
        self.assertEqual(paused.status_code, 200)
        self.assertFalse(paused.data["coupon"]["is_active"])

    @override_settings(MP_ACCESS_TOKEN="APP_USR-production")
    @patch("api.views.get_mercado_pago_sdk")
    @patch("api.views.send_purchase_confirmation_email")
    def test_full_discount_bypasses_mp_and_delivers_pdf_and_email(
        self,
        mocked_email,
        mocked_sdk,
    ):
        mocked_email.return_value = {"sent": True, "id": "email-100", "reason": None}
        coupon = Coupon.objects.create(code="PAOLA100", discount_percent=100)

        response = self.client.post(
            "/api/payments/create-preference",
            self.checkout_payload(coupon.code),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["complimentary"])
        self.assertIn("checkout_token=", response.data["init_point"])
        mocked_sdk.assert_not_called()

        order = Order.objects.get(id=response.data["orderId"])
        coupon.refresh_from_db()
        self.assertEqual(order.status, "completada")
        self.assertEqual(str(order.total), "0.00")
        self.assertEqual(coupon.used_count, 1)
        self.assertEqual(mocked_email.call_count, 1)
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.provider, "coupon")
        self.assertEqual(payment.status, "approved")

        token = response.data["checkoutToken"]
        detail = self.client.get(
            f"/api/orders/{order.id}/guest",
            {"token": token},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["order"]["status"], "completada")
        download = self.client.get(
            f"/api/orders/{order.id}/downloads/{self.product.id}",
            {"token": token},
        )
        self.assertEqual(download.status_code, 302)
        self.assertEqual(download["Location"], self.product.download_url)

    @override_settings(MP_ACCESS_TOKEN="APP_USR-production")
    @patch("api.views.send_purchase_confirmation_email")
    @patch("api.views.get_mercado_pago_sdk")
    def test_partial_discount_waits_for_mp_webhook(
        self,
        mocked_sdk,
        mocked_email,
    ):
        coupon = Coupon.objects.create(code="PAOLA50", discount_percent=50)
        preference = Mock()
        preference.create.return_value = {
            "status": 201,
            "response": {
                "id": "pref-50",
                "init_point": "https://mercadopago.test/checkout",
            },
        }
        mocked_sdk.return_value.preference.return_value = preference

        response = self.client.post(
            "/api/payments/create-preference",
            self.checkout_payload(coupon.code),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(id=response.data["orderId"])
        self.assertEqual(order.status, "pendiente")
        self.assertEqual(str(order.total), "500.00")
        self.assertEqual(
            preference.create.call_args.args[0]["items"][0]["unit_price"],
            500.0,
        )
        mocked_email.assert_not_called()

    @override_settings(MP_ACCESS_TOKEN="APP_USR-production")
    @patch("api.views.send_purchase_confirmation_email")
    @patch("api.views.validate_mercado_pago_webhook_signature", return_value=True)
    @patch("api.views.get_mercado_pago_payment")
    def test_approved_webhook_completes_order_and_sends_email(
        self,
        mocked_payment_lookup,
        _mocked_signature,
        mocked_email,
    ):
        mocked_email.return_value = {"sent": True, "id": "email-mp", "reason": None}
        order = Order.objects.create(
            total="1000.00",
            status="pendiente",
            customer_name="Familia",
            customer_email="familia@example.com",
            preference_id="pref-mp",
            external_reference="",
        )
        order.external_reference = str(order.id)
        order.save(update_fields=["external_reference"])
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price="1000.00",
        )
        mocked_payment_lookup.return_value = (
            {
                "id": "payment-approved",
                "external_reference": str(order.id),
                "transaction_amount": 1000,
                "currency_id": "ARS",
                "status": "approved",
                "preference_id": "pref-mp",
                "payer": {"email": order.customer_email},
            },
            None,
        )

        response = self.client.post(
            "/api/payments/webhook",
            {"data": {"id": "payment-approved"}, "action": "payment.updated"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "completada")
        self.assertEqual(mocked_email.call_count, 1)

    def test_signed_return_token_works_for_registered_buyer_in_new_browser(self):
        user = User.objects.create(
            username="registrada@example.com",
            email="registrada@example.com",
            first_name="Registrada",
            email_verified=True,
            email_verified_at=timezone.now(),
        )
        order = Order.objects.create(
            user=user,
            total="1000.00",
            status="completada",
            customer_name="Registrada",
            customer_email=user.email,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price="1000.00",
        )
        token = make_checkout_return_token(order)

        anonymous_client = APIClient()
        detail = anonymous_client.get(
            f"/api/orders/{order.id}/guest",
            {"token": token},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.data["isGuest"])
        download = anonymous_client.get(
            f"/api/orders/{order.id}/downloads/{self.product.id}",
            {"token": token},
        )
        self.assertEqual(download.status_code, 302)
