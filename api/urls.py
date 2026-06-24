from django.urls import path
from . import views

urlpatterns = [
    path("auth/register", views.register_view, name="register"),
    path("auth/login", views.login_view, name="login"),
    path("auth/logout", views.logout_view, name="logout"),
    path("auth/me", views.me_view, name="me"),
    path("products", views.ProductListCreateView.as_view(), name="products"),
    path("products/<uuid:pk>", views.ProductDetailUpdateDestroyView.as_view(), name="product-detail"),
    path("orders", views.order_list_create_view, name="orders"),
    path("orders/<uuid:pk>", views.order_detail_view, name="order-detail"),
    path("payments/create-preference", views.create_payment_preference_view, name="create-preference"),
    path("payments/webhook", views.payment_webhook_view, name="payment-webhook"),
]
