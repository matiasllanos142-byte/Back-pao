from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .email_service import send_purchase_confirmation_email
from .models import Category, Order, OrderItem, Product, PurchasedProduct


@override_settings(
    MP_ACCESS_TOKEN="",
    BACKEND_PUBLIC_URL="https://backend.test",
    FRONTEND_URL="https://frontend.test",
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
)
class GuestCheckoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Category.objects.create(
            slug="estimulacion",
            name="Estimulación",
            description="Recursos de estimulación.",
            icon="Brain",
            color="#7C3AED",
        )
        self.product = Product.objects.create(
            title="Cuadernillo invitado",
            description="Material descargable.",
            price="2500.00",
            category_id="estimulacion",
            image="/images/products/default.jpg",
            download_url="https://files.test/cuadernillo.pdf",
            download_filename="cuadernillo.pdf",
            age="6-8 años",
            level="Inicial",
            features=[],
            objectives=[],
        )

    @patch("api.views.send_purchase_confirmation_email")
    def test_guest_can_buy_and_use_signed_download_link(self, mocked_email):
        mocked_email.return_value = {"sent": True, "id": "email_guest", "reason": None}

        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(self.product.id), "quantity": 1}],
                "customer": {"email": "familia@gmail.com"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        token = response.data["guestToken"]
        order = Order.objects.get(id=response.data["orderId"])
        self.assertIsNone(order.user)
        self.assertEqual(order.status, "completada")
        self.assertEqual(order.customer_email, "familia@gmail.com")
        self.assertFalse(PurchasedProduct.objects.filter(order=order).exists())
        self.assertEqual(mocked_email.call_count, 1)

        detail = self.client.get(f"/api/orders/{order.id}/guest", {"token": token})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["order"]["customer"]["email"], "familia@gmail.com")

        denied = self.client.get(f"/api/orders/{order.id}/guest", {"token": "invalid"})
        self.assertEqual(denied.status_code, 403)

        download = self.client.get(
            f"/api/orders/{order.id}/downloads/{self.product.id}",
            {"token": token},
        )
        self.assertEqual(download.status_code, 302)
        self.assertEqual(download["Location"], self.product.download_url)
        self.assertEqual(download["Referrer-Policy"], "no-referrer")

    def test_guest_checkout_rejects_invalid_email(self):
        response = self.client.post(
            "/api/payments/create-preference",
            {
                "items": [{"productId": str(self.product.id), "quantity": 1}],
                "customer": {"email": "correo-invalido"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    @patch("api.email_service.send_resend_email")
    def test_guest_confirmation_email_contains_signed_download(self, mocked_send):
        mocked_send.return_value = {"sent": True, "id": "email_rendered", "reason": None}
        order = Order.objects.create(
            user=None,
            total="2500.00",
            status="completada",
            customer_name="Familia",
            customer_email="familia@gmail.com",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price=self.product.price,
        )

        send_purchase_confirmation_email(order)

        message = mocked_send.call_args.args[0]
        self.assertEqual(message["to"], "familia@gmail.com")
        self.assertIn(f"/api/orders/{order.id}/downloads/{self.product.id}", message["html"])
        self.assertIn("Descargar cuadernillo.pdf", message["text"])
        self.assertNotIn("/perfil#biblioteca", message["text"])
