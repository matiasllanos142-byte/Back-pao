import os
from decimal import Decimal
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.conf import settings

from .models import Category, Product, Order, OrderItem
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    CategorySerializer,
    ProductSerializer,
    ProductListSerializer,
    OrderSerializer,
)
from .permissions import IsAdmin

User = get_user_model()

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 días


def set_auth_cookie(response, user):
    token = AccessToken.for_user(user)
    is_secure = not settings.DEBUG
    response.set_cookie(
        COOKIE_NAME,
        str(token),
        httponly=True,
        secure=is_secure,
        samesite="Lax",
        max_age=COOKIE_MAX_AGE,
    )
    return response


def clear_auth_cookie(response):
    response.delete_cookie(COOKIE_NAME)
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    response = Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
    return set_auth_cookie(response, user)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get("email", "").lower().strip()
    password = request.data.get("password", "")

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "Email o contraseña incorrectos."}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.check_password(password):
        return Response({"error": "Email o contraseña incorrectos."}, status=status.HTTP_401_UNAUTHORIZED)

    response = Response(UserSerializer(user).data)
    return set_auth_cookie(response, user)


@api_view(["POST"])
def logout_view(request):
    response = Response({"ok": True})
    return clear_auth_cookie(response)


@api_view(["GET"])
def me_view(request):
    if request.user.is_authenticated:
        return Response({"user": UserSerializer(request.user).data})
    return Response({"user": None})


class ProductListCreateView(generics.ListCreateAPIView):
    queryset = Product.objects.filter(is_active=True).order_by("-created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProductSerializer
        return ProductListSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdmin()]
        return [AllowAny()]


class ProductDetailUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    lookup_field = "pk"

    def get_permissions(self):
        if self.request.method in ["PUT", "PATCH", "DELETE"]:
            return [IsAdmin()]
        return [AllowAny()]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def order_list_create_view(request):
    if request.method == "GET":
        orders = Order.objects.filter(user=request.user).order_by("-created_at")
        serializer = OrderSerializer(orders, many=True)
        return Response({"orders": serializer.data})

    serializer = OrderSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    customer = request.data.get("customer", {})
    customer_name = customer.get("name", "").strip()
    customer_email = customer.get("email", "").lower().strip()

    if not customer_name or not customer_email:
        return Response({"error": "Datos de cliente incompletos."}, status=status.HTTP_400_BAD_REQUEST)

    order = serializer.save(
        user=request.user,
        customer_name=customer_name,
        customer_email=customer_email,
    )
    return Response({"order": OrderSerializer(order).data}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_detail_view(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not request.user.is_admin and order.customer_email != request.user.email:
        return Response({"error": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
    return Response({"order": OrderSerializer(order).data})


@api_view(["POST"])
@permission_classes([AllowAny])
def create_payment_preference_view(request):
    from mercadopago import MercadoPagoConfig, Preference

    items_data = request.data.get("items", [])
    customer = request.data.get("customer", {})
    customer_name = customer.get("name", "").strip()
    customer_email = customer.get("email", "").lower().strip()

    if not items_data or not customer_name or not customer_email:
        return Response({"error": "Datos incompletos."}, status=status.HTTP_400_BAD_REQUEST)

    order_items = []
    for item in items_data:
        try:
            product = Product.objects.get(id=item["productId"], is_active=True)
            quantity = int(item.get("quantity", 1))
            if quantity < 1:
                raise ValueError
            order_items.append({"product": product, "quantity": quantity})
        except (Product.DoesNotExist, ValueError, KeyError):
            return Response({"error": f"Item inválido: {item}"}, status=status.HTTP_400_BAD_REQUEST)

    total = sum(item["product"].price * item["quantity"] for item in order_items)

    order = Order.objects.create(
        user=request.user if request.user.is_authenticated else None,
        total=total,
        status="completada" if not os.environ.get("MP_ACCESS_TOKEN") else "pendiente",
        customer_name=customer_name,
        customer_email=customer_email,
    )

    for item in order_items:
        OrderItem.objects.create(
            order=order,
            product=item["product"],
            quantity=item["quantity"],
            price=item["product"].price,
        )

    base_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")

    if not os.environ.get("MP_ACCESS_TOKEN"):
        return Response({
            "demo": True,
            "orderId": str(order.id),
            "init_point": f"{base_url}/checkout/success?order_id={order.id}",
        })

    client = MercadoPagoConfig(access_token=os.environ.get("MP_ACCESS_TOKEN"))
    preference = Preference(client)

    result = preference.create({
        "body": {
            "items": [
                {
                    "id": str(item["product"].id),
                    "title": item["product"].title,
                    "unit_price": float(item["product"].price),
                    "quantity": item["quantity"],
                    "currency_id": "ARS",
                }
                for item in order_items
            ],
            "payer": {"name": customer_name, "email": customer_email},
            "back_urls": {
                "success": f"{base_url}/checkout/success",
                "failure": f"{base_url}/checkout/failure",
                "pending": f"{base_url}/checkout/failure",
            },
            "auto_return": "approved",
            "external_reference": str(order.id),
        }
    })

    return Response({"init_point": result["init_point"], "orderId": str(order.id)})


@api_view(["POST"])
@permission_classes([AllowAny])
def payment_webhook_view(request):
    body = request.data

    if body.get("type") == "payment" and body.get("data", {}).get("id"):
        payment_data = body["data"]
        order_id = payment_data.get("external_reference")
        payment_status = payment_data.get("status")

        if order_id and payment_status == "approved":
            try:
                order = Order.objects.get(id=order_id)
                order.status = "completada"
                order.payment_id = str(payment_data.get("id"))
                order.save()
            except Order.DoesNotExist:
                pass

    return Response({"ok": True})
