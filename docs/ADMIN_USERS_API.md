# Fuente de usuarios — Dashboard administrativo

Todos los endpoints requieren `admin_session` o Bearer administrativo.

## GET `/api/admin/users`

Query parameters:

```text
page=1
pageSize=20        # 1–100
search=
emailVerified=true|false
status=active|disabled
hasPurchases=true|false
ordering=-created_at|created_at|email|-email|last_login|-last_login
```

Respuesta:

```json
{
  "items": [{
    "id": "uuid",
    "name": "Nombre",
    "email": "persona@example.com",
    "avatarUrl": "https://...",
    "emailVerified": true,
    "isActive": true,
    "createdAt": "ISO-8601",
    "lastLoginAt": "ISO-8601|null",
    "ordersCount": 2,
    "completedOrdersCount": 1,
    "totalSpent": "4500.00",
    "lastOrderAt": "ISO-8601|null",
    "libraryItemsCount": 1,
    "emailsSentCount": 4,
    "emailsFailedCount": 1
  }],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 1,
    "totalPages": 1
  }
}
```

## GET `/api/admin/users/{userId}`

Devuelve perfil, métricas, últimas órdenes, pagos, biblioteca, notificaciones y eventos funcionales.

## Fuentes auxiliares

```text
GET /api/admin/users/{userId}/orders
GET /api/admin/users/{userId}/events
GET /api/admin/users/{userId}/notifications
GET /api/admin/users/{userId}/library
POST /api/admin/orders/{orderId}/resend-email
```

Los eventos registrados son funcionales: registro, login, contraseña, avatar, checkout, pagos, biblioteca, descargas y emails. No existe seguimiento de navegación, mouse ni páginas visitadas.

Las respuestas nunca deben mostrar hashes, tokens, códigos de recuperación, secretos, `raw_metadata` completo de Mercado Pago ni `avatar_public_id`.
