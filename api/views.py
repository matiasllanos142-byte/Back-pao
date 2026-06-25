import os
import hashlib
import time
import base64
from decimal import Decimal
from rest_framework import status, generics
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.core import signing
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import get_object_or_404
from django.conf import settings
import requests

from .models import Category, Product, Order, OrderItem, PurchasedProduct
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    CategorySerializer,
    ProductSerializer,
    ProductListSerializer,
    PurchasedProductSerializer,
    OrderSerializer,
)
from .permissions import IsAdmin
from .permissions import IsEnvAdmin
from .admin_auth import (
    clear_admin_cookie,
    create_admin_token,
    get_admin_from_request,
    set_admin_cookie,
    verify_admin_credentials,
)
from .email_service import EmailDeliveryError, read_email_verification_token, send_verification_email
from .cloudinary_settings import (
    get_cloudinary_credentials,
    resolve_cloudinary_credentials,
    safe_cloudinary_settings,
    save_cloudinary_settings,
)

User = get_user_model()

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 días


def make_auth_token(user):
    return str(AccessToken.for_user(user))


def set_auth_cookie(response, user, token=None):
    token = token or make_auth_token(user)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
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
    email_result = {"sent": False, "id": None, "reason": None}
    try:
        email_result = send_verification_email(user, request)
    except EmailDeliveryError as exc:
        email_result = {"sent": False, "id": None, "reason": str(exc)}

    token = make_auth_token(user)
    response = Response(
        {
            "user": UserSerializer(user).data,
            "accessToken": token,
            "emailVerificationSent": email_result["sent"],
            "emailVerificationError": email_result.get("reason"),
        },
        status=status.HTTP_201_CREATED,
    )
    return set_auth_cookie(response, user, token)


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email_view(request):
    token = request.query_params.get("token", "")
    try:
        payload = read_email_verification_token(token)
        user = User.objects.get(id=payload["user_id"], email=payload["email"])
    except (signing.BadSignature, signing.SignatureExpired, KeyError, User.DoesNotExist):
        if settings.EMAIL_VERIFICATION_ERROR_URL:
            return redirect(settings.EMAIL_VERIFICATION_ERROR_URL)
        return HttpResponse(
            "El enlace de verificacion no es valido o ya expiro.",
            status=400,
            content_type="text/plain; charset=utf-8",
        )

    if not user.email_verified:
        user.mark_email_verified()

    if settings.EMAIL_VERIFICATION_SUCCESS_URL:
        return redirect(settings.EMAIL_VERIFICATION_SUCCESS_URL)

    return HttpResponse(
        "Email verificado correctamente. Ya podes volver a Paola Psicope.",
        content_type="text/plain; charset=utf-8",
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_verification_email_view(request):
    if request.user.email_verified:
        return Response({"ok": True, "emailVerificationSent": False, "alreadyVerified": True})

    try:
        email_result = send_verification_email(request.user, request)
    except EmailDeliveryError:
        return Response({"error": "No se pudo enviar el email de verificacion."}, status=status.HTTP_502_BAD_GATEWAY)

    if not email_result["sent"]:
        return Response(
            {
                "ok": False,
                "emailVerificationSent": False,
                "error": "El envio de emails no esta configurado en el backend.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"ok": True, "emailVerificationSent": email_result["sent"]})


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

    token = make_auth_token(user)
    response = Response({"user": UserSerializer(user).data, "accessToken": token})
    return set_auth_cookie(response, user, token)


@api_view(["POST"])
def logout_view(request):
    response = Response({"ok": True})
    return clear_auth_cookie(response)


@api_view(["GET"])
def me_view(request):
    if request.user.is_authenticated:
        return Response({"user": UserSerializer(request.user).data})
    return Response({"user": None})


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_login_view(request):
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "")

    if not verify_admin_credentials(username, password):
        return Response(
            {"error": "Credenciales de administracion incorrectas."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_admin_token(username)
    response = Response({"admin": {"username": username}, "token": token, "accessToken": token})
    return set_admin_cookie(response, token)


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_logout_view(request):
    response = Response({"ok": True})
    return clear_admin_cookie(response)


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_me_view(request):
    admin = get_admin_from_request(request)
    return Response({"admin": admin})


def sign_cloudinary_upload(params, api_secret):
    payload = "&".join(
        f"{key}={value}"
        for key, value in sorted(params.items())
        if value not in [None, ""]
    )
    return hashlib.sha1(f"{payload}{api_secret}".encode("utf-8")).hexdigest()


def cloudinary_error(response, fallback):
    try:
        data = response.json()
        message = data.get("error", {}).get("message")
        return message or fallback
    except ValueError:
        return fallback


@api_view(["GET", "PUT"])
@permission_classes([IsEnvAdmin])
def admin_cloudinary_settings_view(request):
    if request.method == "GET":
        return Response({"cloudinary": safe_cloudinary_settings()})

    cloud_name = request.data.get("cloudName", "").strip()
    api_key = request.data.get("apiKey", "").strip()
    api_secret = request.data.get("apiSecret", "").strip()

    if not cloud_name or not api_key:
        return Response(
            {"error": "Cloud name y API key son obligatorios."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        instance = save_cloudinary_settings(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret or None,
        )
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"cloudinary": safe_cloudinary_settings(instance)})


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
def admin_cloudinary_settings_test_view(request):
    credentials = resolve_cloudinary_credentials(request.data)
    if not credentials:
        return Response(
            {"error": "Completa las credenciales de Cloudinary."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    auth = base64.b64encode(
        f"{credentials['api_key']}:{credentials['api_secret']}".encode("utf-8")
    ).decode("ascii")
    usage_url = f"https://api.cloudinary.com/v1_1/{credentials['cloud_name']}/usage"

    try:
        response = requests.get(
            usage_url,
            headers={"Authorization": f"Basic {auth}"},
            timeout=20,
        )
    except requests.RequestException:
        return Response(
            {"error": "No se pudo validar Cloudinary."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if response.status_code >= 400:
        return Response(
            {"error": cloudinary_error(response, "Cloudinary rechazo las credenciales.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({"ok": True})


def grant_order_access(order):
    if not order.user_id or order.status != "completada":
        return

    for item in order.items.select_related("product"):
        PurchasedProduct.objects.update_or_create(
            user=order.user,
            product=item.product,
            defaults={
                "order": order,
                "is_active": True,
            },
        )


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
@parser_classes([MultiPartParser, FormParser])
def admin_image_upload_view(request):
    image = request.FILES.get("image")
    if not image:
        return Response({"error": "Falta la imagen."}, status=status.HTTP_400_BAD_REQUEST)

    if not image.content_type.startswith("image/"):
        return Response({"error": "El archivo debe ser una imagen."}, status=status.HTTP_400_BAD_REQUEST)

    if image.size > settings.CLOUDINARY_MAX_UPLOAD_BYTES:
        return Response({"error": "La imagen supera el tamano maximo permitido."}, status=status.HTTP_400_BAD_REQUEST)

    credentials = get_cloudinary_credentials()
    if not credentials:
        return Response(
            {"error": "Configura Cloudinary en Ajustes antes de subir imagenes."},
            status=status.HTTP_409_CONFLICT,
        )

    timestamp = int(time.time())
    upload_params = {
        "timestamp": timestamp,
        "folder": settings.CLOUDINARY_UPLOAD_FOLDER,
    }
    signature = sign_cloudinary_upload(upload_params, credentials["api_secret"])
    upload_url = f"https://api.cloudinary.com/v1_1/{credentials['cloud_name']}/image/upload"

    try:
        response = requests.post(
            upload_url,
            data={
                **{key: value for key, value in upload_params.items() if value},
                "api_key": credentials["api_key"],
                "signature": signature,
            },
            files={"file": (image.name, image.file, image.content_type)},
            timeout=30,
        )
    except requests.RequestException:
        return Response({"error": "No se pudo subir la imagen."}, status=status.HTTP_502_BAD_GATEWAY)

    if response.status_code >= 400:
        return Response(
            {"error": cloudinary_error(response, "Cloudinary rechazo la imagen.")},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    data = response.json()
    secure_url = data.get("secure_url")
    if not secure_url:
        return Response({"error": "Cloudinary no devolvio una URL valida."}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(
        {
            "url": secure_url,
            "publicId": data.get("public_id"),
        }
    )


@api_view(["POST"])
@permission_classes([IsEnvAdmin])
@parser_classes([MultiPartParser, FormParser])
def admin_download_upload_view(request):
    file = request.FILES.get("file")
    if not file:
        return Response({"error": "Falta el archivo."}, status=status.HTTP_400_BAD_REQUEST)

    allowed_types = {
        "application/pdf",
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    }
    if file.content_type not in allowed_types:
        return Response(
            {"error": "El archivo debe ser PDF o ZIP."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if file.size > settings.CLOUDINARY_MAX_DOWNLOAD_BYTES:
        return Response({"error": "El archivo supera el tamano maximo permitido."}, status=status.HTTP_400_BAD_REQUEST)

    credentials = get_cloudinary_credentials()
    if not credentials:
        return Response(
            {"error": "Configura Cloudinary en Ajustes antes de subir archivos."},
            status=status.HTTP_409_CONFLICT,
        )

    timestamp = int(time.time())
    upload_params = {
        "timestamp": timestamp,
        "folder": settings.CLOUDINARY_DOWNLOAD_FOLDER,
    }
    signature = sign_cloudinary_upload(upload_params, credentials["api_secret"])
    upload_url = f"https://api.cloudinary.com/v1_1/{credentials['cloud_name']}/raw/upload"

    try:
        response = requests.post(
            upload_url,
            data={
                **{key: value for key, value in upload_params.items() if value},
                "api_key": credentials["api_key"],
                "signature": signature,
            },
            files={"file": (file.name, file.file, file.content_type)},
            timeout=60,
        )
    except requests.RequestException:
        return Response({"error": "No se pudo subir el archivo."}, status=status.HTTP_502_BAD_GATEWAY)

    if response.status_code >= 400:
        return Response(
            {"error": cloudinary_error(response, "Cloudinary rechazo el archivo.")},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    data = response.json()
    secure_url = data.get("secure_url")
    if not secure_url:
        return Response({"error": "Cloudinary no devolvio una URL valida."}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(
        {
            "url": secure_url,
            "fileName": file.name,
            "publicId": data.get("public_id"),
        }
    )


class ProductListCreateView(generics.ListCreateAPIView):
    queryset = Product.objects.filter(is_active=True).order_by("-created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProductSerializer
        return ProductListSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsEnvAdmin()]
        return [AllowAny()]


class ProductDetailUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    lookup_field = "pk"

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ProductListSerializer
        return ProductSerializer

    def get_permissions(self):
        if self.request.method in ["PUT", "PATCH", "DELETE"]:
            return [IsEnvAdmin()]
        return [AllowAny()]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()


class AdminProductListCreateView(ProductListCreateView):
    permission_classes = [IsEnvAdmin]

    def get_permissions(self):
        return [IsEnvAdmin()]


class AdminProductDetailUpdateDestroyView(ProductDetailUpdateDestroyView):
    permission_classes = [IsEnvAdmin]

    def get_permissions(self):
        return [IsEnvAdmin()]


@api_view(["GET"])
@permission_classes([IsEnvAdmin])
def admin_order_list_view(request):
    orders = Order.objects.all().order_by("-created_at")[:100]
    serializer = OrderSerializer(orders, many=True)
    return Response({"orders": serializer.data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def library_view(request):
    purchases = (
        PurchasedProduct.objects.filter(user=request.user, is_active=True)
        .select_related("product", "order", "product__category")
        .order_by("-acquired_at")
    )
    serializer = PurchasedProductSerializer(purchases, many=True)
    return Response({"items": serializer.data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def library_download_view(request, pk):
    purchase = get_object_or_404(
        PurchasedProduct.objects.select_related("product"),
        user=request.user,
        product_id=pk,
        is_active=True,
    )
    if not purchase.product.download_url:
        return Response(
            {"error": "Este producto todavia no tiene archivo descargable."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "downloadUrl": purchase.product.download_url,
            "downloadFileName": purchase.product.download_filename,
        }
    )


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
@permission_classes([IsAuthenticated])
def create_payment_preference_view(request):
    items_data = request.data.get("items", [])
    customer = request.data.get("customer", {})
    customer_name = customer.get("name", "").strip() or request.user.first_name
    customer_email = request.user.email.lower().strip()

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
        user=request.user,
        total=total,
        status="completada" if not settings.MP_ACCESS_TOKEN else "pendiente",
        customer_name=customer_name,
        customer_email=customer_email,
        external_reference="",
    )
    order.external_reference = str(order.id)
    order.save(update_fields=["external_reference", "updated_at"])

    for item in order_items:
        OrderItem.objects.create(
            order=order,
            product=item["product"],
            quantity=item["quantity"],
            price=item["product"].price,
        )

    base_url = settings.FRONTEND_URL

    if not settings.MP_ACCESS_TOKEN:
        grant_order_access(order)
        return Response({
            "demo": True,
            "orderId": str(order.id),
            "init_point": f"{base_url}/checkout/success?order_id={order.id}",
        })

    import mercadopago

    sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
    result = sdk.preference().create({
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

    response_body = result.get("response", {})
    init_point = response_body.get("init_point")
    if not init_point:
        return Response(
            {"error": "Mercado Pago no devolvio un link de pago."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({"init_point": init_point, "orderId": str(order.id)})


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
                order.save(update_fields=["status", "payment_id", "updated_at"])
                grant_order_access(order)
            except Order.DoesNotExist:
                pass

    return Response({"ok": True})
