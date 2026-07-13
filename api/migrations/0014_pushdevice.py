# Generated manually for Firebase Cloud Messaging device registration.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0013_notification_payment_paymentevent_userevent_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PushDevice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("token", models.CharField(max_length=512, unique=True)),
                ("platform", models.CharField(choices=[("android", "Android")], default="android", max_length=20)),
                ("device_name", models.CharField(blank=True, max_length=120)),
                ("app_version", models.CharField(blank=True, max_length=40)),
                ("active", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_devices", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "push_devices"},
        ),
        migrations.AddIndex(
            model_name="pushdevice",
            index=models.Index(fields=["user", "active"], name="push_user_active_idx"),
        ),
        migrations.AddIndex(
            model_name="pushdevice",
            index=models.Index(fields=["platform", "active"], name="push_platform_active_idx"),
        ),
    ]
