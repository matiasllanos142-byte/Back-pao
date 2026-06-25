from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from .models import Category, Product, Order, OrderItem

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="first_name")
    isAdmin = serializers.BooleanField(source="is_admin")
    emailVerified = serializers.BooleanField(source="email_verified")
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = User
        fields = ["id", "name", "email", "isAdmin", "emailVerified", "createdAt"]


class RegisterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(write_only=True, required=False, allow_blank=False)
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["name", "first_name", "email", "password"]
        extra_kwargs = {
            "first_name": {"write_only": True, "required": False, "allow_blank": False}
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


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["slug", "name", "description", "icon", "color"]


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(
        queryset=Category.objects.all(), slug_field="slug"
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "description",
            "price",
            "category",
            "image",
            "badge",
            "featured",
            "age",
            "level",
            "features",
            "objectives",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(read_only=True, slug_field="slug")

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "description",
            "price",
            "category",
            "image",
            "badge",
            "featured",
            "age",
            "level",
            "features",
            "objectives",
            "created_at",
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
            "customer",
            "items",
            "created_at",
        ]

    def get_customer(self, obj):
        return {"name": obj.customer_name, "email": obj.customer_email}

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
