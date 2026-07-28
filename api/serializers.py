from decimal import Decimal, InvalidOperation

from django.utils.text import slugify
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from .models import (
    Category,
    Coupon,
    Notification,
    Order,
    OrderItem,
    Product,
    PurchasedProduct,
    UserEvent,
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="first_name")
    isAdmin = serializers.BooleanField(source="is_admin")
    emailVerified = serializers.BooleanField(source="email_verified")
    createdAt = serializers.DateTimeField(source="created_at")
    avatarUrl = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    lastLoginAt = serializers.DateTimeField(source="last_login", allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "isAdmin",
            "emailVerified",
            "avatarUrl",
            "phone",
            "createdAt",
            "lastLoginAt",
        ]

    def get_avatarUrl(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.avatar_url if profile else ""

    def get_phone(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.phone if profile else ""


class RegisterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(write_only=True, required=False, allow_blank=False)
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["name", "first_name", "email", "password"]
        extra_kwargs = {
            "email": {"validators": []},
            "first_name": {"write_only": True, "required": False, "allow_blank": False},
        }

    def validate(self, attrs):
        if not attrs.get("name") and not attrs.get("first_name"):
            raise serializers.ValidationError({"name": "Este campo es requerido."})
        return attrs

    def create(self, validated_data):
        email = validated_data["email"].lower()
        first_name = validated_data.get("name") or validated_data.get("first_name", "")

        user = User.objects.create(
            username=email,
            email=email,
            first_name=first_name,
            is_admin=False,
            password=make_password(validated_data["password"]),
        )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(required=True, trim_whitespace=False)
    newPassword = serializers.CharField(required=True, min_length=8, trim_whitespace=False)
    confirmPassword = serializers.CharField(required=True, trim_whitespace=False)

    def validate_currentPassword(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contrasena actual es incorrecta.")
        return value

    def validate(self, attrs):
        if attrs["newPassword"] != attrs["confirmPassword"]:
            raise serializers.ValidationError({"confirmPassword": "Las contrasenas no coinciden."})
        if attrs["currentPassword"] == attrs["newPassword"]:
            raise serializers.ValidationError({"newPassword": "La nueva contrasena debe ser diferente a la actual."})
        return attrs


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["slug", "name", "description", "icon", "color"]


DEFAULT_CATEGORY_META = {
    "estimulacion": ("Estimulacion Cognitiva", "Brain", "#7C3AED"),
    "lectoescritura": ("Lectoescritura", "BookOpen", "#F97316"),
    "dislexia": ("Dislexia", "BookMarked", "#22C55E"),
    "discalculia": ("Discalculia", "Calculator", "#0EA5E9"),
    "matematica": ("Matematica", "Calculator", "#06B6D4"),
    "atencion-memoria": ("Atencion y Memoria", "Eye", "#EC4899"),
    "funciones-ejecutivas": ("Funciones Ejecutivas", "Puzzle", "#FBBF24"),
    "tdah": ("TDAH", "Zap", "#F59E0B"),
    "tea-autismo": ("TEA / Autismo", "Sparkles", "#14B8A6"),
    "lenguaje": ("Lenguaje", "MessageCircle", "#8B5CF6"),
    "emociones": ("Emociones", "Heart", "#EF4444"),
    "habilidades-sociales": ("Habilidades Sociales", "Users", "#10B981"),
    "habitos-estudio": ("Habitos de Estudio", "NotebookTabs", "#6366F1"),
    "percepcion-visual": ("Percepcion Visual", "Eye", "#EC4899"),
    "motricidad-fina": ("Motricidad Fina", "Pencil", "#84CC16"),
}


def normalize_money(value):
    if value in ("", None):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    cleaned = (
        str(value)
        .strip()
        .replace("$", "")
        .replace("ARS", "")
        .replace(" ", "")
    )
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "." in cleaned:
        pieces = cleaned.split(".")
        if len(pieces) > 1 and all(len(piece) == 3 for piece in pieces[1:]):
            cleaned = "".join(pieces)

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise serializers.ValidationError("El precio no tiene un formato valido.") from exc


def category_name_from_value(value, slug):
    text = str(value or "").strip()
    if text and text != slug:
        return text
    if slug in DEFAULT_CATEGORY_META:
        return DEFAULT_CATEGORY_META[slug][0]
    return slug.replace("-", " ").title()


class CategorySlugField(serializers.Field):
    def to_representation(self, value):
        return value.slug if value else ""

    def to_internal_value(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("La categoria es obligatoria.")

        original = str(value).strip()
        slug = slugify(original)[:100] or "sin-categoria"
        default_name, default_icon, default_color = DEFAULT_CATEGORY_META.get(
            slug,
            (category_name_from_value(original, slug), "Package", "#7C3AED"),
        )
        category, created = Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name": default_name,
                "description": f"Recursos de {default_name}.",
                "icon": default_icon,
                "color": default_color,
            },
        )
        if not created and original != slug and category.name != original:
            category.name = original
            category.save(update_fields=["name"])
        return category


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySlugField()
    price = serializers.CharField()
    compare_at_price = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "description",
            "price",
            "compare_at_price",
            "category",
            "product_type",
            "image",
            "image_public_id",
            "download_url",
            "download_filename",
            "download_public_id",
            "download_content_type",
            "download_size",
            "badge",
            "featured",
            "age",
            "level",
            "features",
            "objectives",
            "metadata",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_price(self, value):
        money = normalize_money(value)
        if money is None:
            raise serializers.ValidationError("El precio es obligatorio.")
        if money < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        return money

    def validate_compare_at_price(self, value):
        money = normalize_money(value)
        if money is not None and money < 0:
            raise serializers.ValidationError("El precio anterior no puede ser negativo.")
        return money

    def validate(self, attrs):
        price = attrs.get("price", getattr(self.instance, "price", None))
        compare_at_price = attrs.get(
            "compare_at_price",
            getattr(self.instance, "compare_at_price", None),
        )
        if compare_at_price is not None and price is not None and compare_at_price <= price:
            raise serializers.ValidationError(
                {"compare_at_price": "El precio anterior debe ser mayor al precio actual."}
            )
        return attrs


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    galleryImages = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "description",
            "price",
            "compare_at_price",
            "category",
            "product_type",
            "image",
            "badge",
            "featured",
            "age",
            "level",
            "features",
            "objectives",
            "created_at",
            "galleryImages",
        ]

    def get_galleryImages(self, obj):
        raw = obj.metadata.get("gallery_images", []) if isinstance(obj.metadata, dict) else []
        if not isinstance(raw, list):
            return []
        sanitized = []
        for item in raw:
            if isinstance(item, dict) and item.get("url"):
                sanitized.append({
                    "url": item["url"],
                    "fileName": item.get("fileName", ""),
                    "order": item.get("order", 0),
                })
        sanitized.sort(key=lambda x: x["order"])
        return sanitized


class CouponSerializer(serializers.ModelSerializer):
    code = serializers.CharField(max_length=80)
    usesRemaining = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "discount_percent",
            "is_active",
            "starts_at",
            "expires_at",
            "max_uses",
            "used_count",
            "usesRemaining",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "used_count", "usesRemaining", "created_at", "updated_at"]

    def validate_code(self, value):
        normalized = str(value or "").strip().upper()
        if len(normalized) < 3:
            raise serializers.ValidationError("El codigo debe tener al menos 3 caracteres.")
        return normalized

    def validate_max_uses(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("El limite de usos debe ser mayor a cero.")
        return value

    def validate(self, attrs):
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        expires_at = attrs.get("expires_at", getattr(self.instance, "expires_at", None))
        if starts_at and expires_at and expires_at <= starts_at:
            raise serializers.ValidationError(
                {"expires_at": "El vencimiento debe ser posterior al inicio."}
            )
        max_uses = attrs.get("max_uses", getattr(self.instance, "max_uses", None))
        used_count = getattr(self.instance, "used_count", 0)
        if max_uses is not None and max_uses < used_count:
            raise serializers.ValidationError(
                {"max_uses": "El limite no puede ser menor que los usos ya registrados."}
            )
        return attrs

    def get_usesRemaining(self, obj):
        if obj.max_uses is None:
            return None
        return max(obj.max_uses - obj.used_count, 0)


class PurchasedProductSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    downloadUrl = serializers.CharField(source="product.download_url", read_only=True)
    downloadFileName = serializers.CharField(
        source="product.download_filename", read_only=True
    )
    acquiredAt = serializers.DateTimeField(source="acquired_at", read_only=True)
    orderId = serializers.UUIDField(source="order_id", read_only=True)

    class Meta:
        model = PurchasedProduct
        fields = [
            "id",
            "product",
            "downloadUrl",
            "downloadFileName",
            "acquiredAt",
            "orderId",
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = OrderItem
        fields = ["product", "product_id", "quantity", "price"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    customer = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "total",
            "status",
            "preference_id",
            "payment_id",
            "external_reference",
            "customer",
            "promo_code",
            "discount_amount",
            "items",
            "created_at",
        ]
        read_only_fields = ["preference_id", "payment_id", "external_reference", "created_at"]

    def get_customer(self, obj):
        return {
            "name": obj.customer_name,
            "email": obj.customer_email,
            "phone": obj.customer_phone,
        }

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        order = Order.objects.create(**validated_data)

        total = 0
        for item_data in items_data:
            product = Product.objects.get(id=item_data["product_id"], is_active=True)
            quantity = item_data["quantity"]
            price = product.price
            OrderItem.objects.create(
                order=order, product=product, quantity=quantity, price=price
            )
            total += price * quantity

        order.total = total
        order.save(update_fields=["total"])
        return order


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "type", "channel", "recipient", "status",
            "provider_message_id", "attempts",
            "sent_at", "delivered_at", "failed_at", "error_message",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserEvent
        fields = ["id", "event_type", "entity_type", "entity_id", "metadata", "created_at"]
        read_only_fields = ["id", "created_at"]
