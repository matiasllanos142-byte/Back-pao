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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", db_column="category_slug"
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
