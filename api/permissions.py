from rest_framework.permissions import BasePermission

from .admin_auth import get_admin_from_request


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class IsEnvAdmin(BasePermission):
    message = "Credenciales de administracion requeridas."

    def has_permission(self, request, view):
        admin = get_admin_from_request(request)
        if admin:
            request.admin = admin
            return True
        return False
