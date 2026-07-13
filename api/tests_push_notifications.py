from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import PushDevice


User = get_user_model()


class PushDeviceApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="push-user",
            email="push@example.com",
            password="safe-password-123",
            email_verified=True,
        )
        self.client.force_authenticate(self.user)

    def test_registers_and_refreshes_android_device(self):
        response = self.client.post(
            "/api/notifications/device",
            {
                "token": "test-fcm-token",
                "deviceName": "Pixel test",
                "appVersion": "1.1.0",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        device = PushDevice.objects.get(token="test-fcm-token")
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.platform, "android")
        self.assertTrue(device.active)

    def test_unregister_marks_device_inactive(self):
        PushDevice.objects.create(user=self.user, token="token-to-remove")

        response = self.client.delete(
            "/api/notifications/device",
            {"token": "token-to-remove"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["removed"])
        self.assertFalse(PushDevice.objects.get(token="token-to-remove").active)

    def test_rejects_missing_token(self):
        response = self.client.post("/api/notifications/device", {}, format="json")

        self.assertEqual(response.status_code, 400)
