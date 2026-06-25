from django.urls import path
from . import views

urlpatterns = [
    path("admin/login", views.admin_login_view, name="admin-login"),
    path("admin/logout", views.admin_logout_view, name="admin-logout"),
    path("admin/me", views.admin_me_view, name="admin-me"),
    path("admin/products", views.AdminProductListCreateView.as_view(), name="admin-products"),
    path("admin/products/<uuid:pk>", views.AdminProductDetailUpdateDestroyView.as_view(), name="admin-product-detail"),
    path("admin/orders", views.admin_order_list_view, name="admin-orders"),
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
