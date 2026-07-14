import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    is_admin = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    auth_token_version = models.IntegerField(default=0)
    disabled_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email

    def mark_email_verified(self):
        self.email_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_verified", "email_verified_at", "updated_at"])

    def increment_token_version(self):
        self.auth_token_version += 1
        self.save(update_fields=["auth_token_version", "updated_at"])


class UserProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar_url = models.CharField(max_length=500, blank=True)
    avatar_public_id = models.CharField(max_length=500, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"

    def __str__(self):
        return f"Profile for {self.user.email}"


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name="payments")
    provider = models.CharField(max_length=50, default="mercadopago")
    provider_payment_id = models.CharField(max_length=200, unique=True)
    preference_id = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=50)
    status_detail = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="ARS")
    payer_email = models.EmailField(blank=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    raw_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        verbose_name_plural = "payments"
        indexes = [
            models.Index(fields=["provider_payment_id"]),
            models.Index(fields=["order", "status"]),
        ]

    def __str__(self):
        return f"Payment {self.provider_payment_id} - {self.status}"


class PaymentEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=50, default="mercadopago")
    provider_event_id = models.CharField(max_length=200, blank=True)
    provider_payment_id = models.CharField(max_length=200, blank=True)
    event_type = models.CharField(max_length=100)
    action = models.CharField(max_length=100, blank=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "payment_events"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_event_id"],
                condition=~models.Q(provider_event_id=""),
                name="unique_provider_payment_event",
            )
        ]
        indexes = [
            models.Index(fields=["provider_payment_id", "event_type"]),
            models.Index(fields=["payload_hash"]),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.provider_payment_id}"


class Notification(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    order = models.ForeignKey("Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    type = models.CharField(max_length=100)
    channel = models.CharField(max_length=50, default="email")
    recipient = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    provider_message_id = models.CharField(max_length=300, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["user", "type"]),
            models.Index(fields=["order", "type"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.type} -> {self.recipient} [{self.status}]"


class PushDevice(models.Model):
    PLATFORM_CHOICES = [("android", "Android")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_devices")
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default="android")
    device_name = models.CharField(max_length=120, blank=True)
    app_version = models.CharField(max_length=40, blank=True)
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "push_devices"
        indexes = [
            models.Index(fields=["user", "active"], name="push_user_active_idx"),
            models.Index(fields=["platform", "active"], name="push_platform_active_idx"),
        ]

    def __str__(self):
        return f"{self.user.email} [{self.platform}]"


class UserEvent(models.Model):
    EVENT_TYPES = [
        ("account_registered", "Account Registered"),
        ("email_verified", "Email Verified"),
        ("login", "Login"),
        ("logout", "Logout"),
        ("password_changed", "Password Changed"),
        ("password_reset", "Password Reset"),
        ("avatar_updated", "Avatar Updated"),
        ("avatar_deleted", "Avatar Deleted"),
        ("checkout_started", "Checkout Started"),
        ("payment_pending", "Payment Pending"),
        ("payment_approved", "Payment Approved"),
        ("payment_rejected", "Payment Rejected"),
        ("payment_refunded", "Payment Refunded"),
        ("library_access_granted", "Library Access Granted"),
        ("material_downloaded", "Material Downloaded"),
        ("email_queued", "Email Queued"),
        ("email_sent", "Email Sent"),
        ("email_failed", "Email Failed"),
        ("profile_updated", "Profile Updated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    entity_type = models.CharField(max_length=50, blank=True)
    entity_id = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_events"
        indexes = [
            models.Index(fields=["user", "event_type"]),
            models.Index(fields=["event_type", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} - {self.user_id}"


class PendingRegistration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=300)
    password_hash = models.CharField(max_length=200)
    verification_code_hash = models.CharField(max_length=200)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pending_registrations"

    def __str__(self):
        return self.email

    def is_expired(self):
        return timezone.now() >= self.expires_at


class PasswordResetRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_requests")
    email = models.EmailField()
    verification_code_hash = models.CharField(max_length=200)
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "password_reset_requests"
        indexes = [
            models.Index(fields=["email", "created_at"]),
        ]

    def __str__(self):
        return self.email

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def is_usable(self):
        return self.used_at is None and not self.is_expired()


class Category(models.Model):
    slug = models.SlugField(primary_key=True, max_length=100)
    name = models.CharField(max_length=200)
    description = models.TextField()
    icon = models.CharField(max_length=100)
    color = models.CharField(max_length=50)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    PRODUCT_TYPE_PRODUCT = "product"
    PRODUCT_TYPE_WORKSHOP = "workshop"
    PRODUCT_TYPE_CHOICES = [
        (PRODUCT_TYPE_PRODUCT, "Producto digital"),
        (PRODUCT_TYPE_WORKSHOP, "Taller"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", db_column="category_slug"
    )
    product_type = models.CharField(
        max_length=20,
        choices=PRODUCT_TYPE_CHOICES,
        default=PRODUCT_TYPE_PRODUCT,
        db_index=True,
    )
    image = models.CharField(max_length=500, default="/images/products/placeholder.jpg")
    image_public_id = models.CharField(max_length=500, blank=True)
    download_url = models.URLField(max_length=1000, blank=True)
    download_filename = models.CharField(max_length=300, blank=True)
    download_public_id = models.CharField(max_length=500, blank=True)
    download_content_type = models.CharField(max_length=200, blank=True)
    download_size = models.PositiveBigIntegerField(blank=True, null=True)
    badge = models.CharField(max_length=100, blank=True, null=True)
    featured = models.BooleanField(default=False)
    age = models.CharField(max_length=100)
    level = models.CharField(max_length=100)
    features = models.JSONField(default=list)
    objectives = models.JSONField(default=list)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"

    def __str__(self):
        return self.title


class CloudinarySettings(models.Model):
    id = models.CharField(primary_key=True, max_length=50, default="cloudinary")
    cloud_name = models.CharField(max_length=200)
    api_key = models.CharField(max_length=200)
    api_secret_encrypted = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cloudinary_settings"
        verbose_name = "Cloudinary settings"
        verbose_name_plural = "Cloudinary settings"

    def __str__(self):
        return self.cloud_name


class NvidiaSettings(models.Model):
    id = models.CharField(primary_key=True, max_length=50, default="nvidia")
    api_key_encrypted = models.TextField(blank=True)
    base_url = models.URLField(max_length=500, default="https://integrate.api.nvidia.com/v1")
    model = models.CharField(max_length=300, blank=True)
    image_model = models.CharField(max_length=300, blank=True)
    workbook_skill = models.TextField(blank=True)
    workbook_plan_model = models.CharField(max_length=300, blank=True)
    workbook_build_model = models.CharField(max_length=300, blank=True)
    model_catalog = models.JSONField(default=dict, blank=True)
    model_roles = models.JSONField(default=dict, blank=True)
    model_catalog_refreshed_at = models.DateTimeField(blank=True, null=True)
    model_catalog_last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nvidia_settings"
        verbose_name = "NVIDIA settings"
        verbose_name_plural = "NVIDIA settings"

    def __str__(self):
        return self.base_url


class WorkbookDraft(models.Model):
    STATUS_CHOICES = [
        ("planned", "Planned"),
        ("building", "Building"),
        ("done", "Done"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    brief = models.TextField(blank=True)
    topic = models.CharField(max_length=200, blank=True)
    age = models.CharField(max_length=100, blank=True)
    difficulty = models.CharField(max_length=100, blank=True)
    pages = models.PositiveIntegerField(default=20)
    style = models.CharField(max_length=200, blank=True)
    provider = models.CharField(max_length=100, default="local")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planned")
    plan = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workbook_drafts"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class PurchasedProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="purchased_products"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="purchases"
    )
    order = models.ForeignKey(
        "Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="accesses"
    )
    is_active = models.BooleanField(default=True)
    acquired_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchased_products"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                condition=models.Q(is_active=True),
                name="unique_active_product_access_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.product.title}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("pendiente", "Pendiente"),
        ("completada", "Completada"),
        ("fallida", "Fallida"),
        ("reembolsada", "Reembolsada"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendiente")
    customer_name = models.CharField(max_length=300)
    customer_email = models.EmailField()
    preference_id = models.CharField(max_length=200, blank=True, null=True)
    payment_id = models.CharField(max_length=200, blank=True, null=True)
    external_reference = models.CharField(max_length=200, blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    purchase_email_sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders"

    def __str__(self):
        return f"Order {self.id} - {self.status}"


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "order_items"

    def __str__(self):
        return f"{self.product.title} x {self.quantity}"
