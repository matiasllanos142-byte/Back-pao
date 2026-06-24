from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from .models import Category, Product, Order, OrderItem

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "is_admin", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["first_name", "email", "password"]

    def create(self, validated_data):
        from django.conf import settings

        email = validated_data["email"].lower()
        admin_email = getattr(settings, "ADMIN_EMAIL", "admin@paolapsicope.com")
        is_admin = email == admin_email.lower()

        user = User.objects.create(
            username=email,
            email=email,
            first_name=validated_data.get("first_name", ""),
            is_admin=is_admin,
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
