from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Category, Product, Order, OrderItem, CloudinarySettings, PendingRegistration


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "first_name", "is_admin", "is_active", "created_at"]
    list_filter = ["is_admin", "is_active", "is_staff", "is_superuser"]
    search_fields = ["email", "first_name"]
    ordering = ["-created_at"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "username")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "is_admin", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "password1", "password2", "is_admin"),
        }),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["slug", "name", "color"]
    search_fields = ["name", "slug"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "price", "featured", "is_active", "created_at"]
    list_filter = ["category", "featured", "is_active", "level"]
    search_fields = ["title", "description"]


@admin.register(CloudinarySettings)
class CloudinarySettingsAdmin(admin.ModelAdmin):
    list_display = ["cloud_name", "api_key", "updated_at"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(PendingRegistration)
class PendingRegistrationAdmin(admin.ModelAdmin):
    list_display = ["email", "name", "attempts", "expires_at", "created_at"]
    search_fields = ["email", "name"]
    readonly_fields = ["created_at", "updated_at"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "quantity", "price"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer_email", "total", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["customer_email", "customer_name"]
    inlines = [OrderItemInline]
