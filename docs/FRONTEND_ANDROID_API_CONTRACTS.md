# Contratos API — Web y Android

Base web:

```text
https://<BACKEND_PUBLIC_URL>/api
```

En Retrofit la base debe terminar en `/api/`.

## Autenticación

La web puede usar cookie HttpOnly `session` con `credentials: "include"`. Android debe enviar:

```http
Authorization: Bearer <accessToken>
```

### GET `/auth/me`

```json
{
  "user": {
    "id": "uuid",
    "name": "Nombre",
    "email": "persona@example.com",
    "isAdmin": false,
    "emailVerified": true,
    "avatarUrl": "https://...",
    "phone": "",
    "createdAt": "ISO-8601",
    "lastLoginAt": "ISO-8601|null"
  }
}
```

Sin sesión devuelve `{"user": null}`.

### PATCH `/auth/change-password`

```json
{
  "currentPassword": "actual",
  "newPassword": "nueva-segura",
  "confirmPassword": "nueva-segura"
}
```

Éxito `200`:

```json
{"ok": true, "message": "Contrasena actualizada. Inicia sesion nuevamente."}
```

El backend invalida tokens anteriores y elimina la cookie. El cliente debe cerrar la sesión local y mostrar login.

### PATCH `/auth/avatar`

`multipart/form-data`, campo `avatar`. Formatos JPEG, PNG o WebP. Máximo definido por `CLOUDINARY_AVATAR_MAX_BYTES`.

```json
{"avatarUrl": "https://..."}
```

### DELETE `/auth/avatar`

```json
{"ok": true, "deleted": true}
```

Si no hay avatar: `200`, `deleted:false`. Si Cloudinary no confirma la eliminación: `502` y la base conserva el avatar.

## Checkout

### POST `/payments/create-preference`

```json
{
  "items": [{"productId": "uuid", "quantity": 1}],
  "customer": {"name": "Nombre"}
}
```

El backend ignora precios y email enviados por el cliente; obtiene precios desde PostgreSQL y usa el email autenticado.

Éxito:

```json
{
  "init_point": "https://www.mercadopago.com/...",
  "orderId": "uuid",
  "preferenceId": "...",
  "notificationUrl": "https://.../api/payments/webhook?source_news=webhooks",
  "mpMode": "production"
}
```

Guardar `orderId` antes de abrir Mercado Pago.

### GET `/orders/{orderId}/status`

```json
{
  "orderId": "uuid",
  "status": "pending|approved|rejected|refunded",
  "paymentStatus": "pending|approved|rejected|cancelled|refunded|null",
  "libraryReady": true,
  "emailStatus": "pending|sent|failed|null",
  "redirectTo": "/perfil?payment=approved",
  "updatedAt": "ISO-8601"
}
```

Hacer polling cada 2–3 segundos, máximo 60 segundos. Solo vaciar carrito cuando:

```text
status == "approved" && libraryReady == true
```

No aprobar una compra usando parámetros de la URL de retorno.

Retornos que el frontend debe implementar:

```text
/checkout/success?order_id=<uuid>
/checkout/pending?order_id=<uuid>
/checkout/failure?order_id=<uuid>
```

### GET `/orders`

Devuelve las órdenes del usuario autenticado.

### GET `/library`

```json
{"items": []}
```

### GET `/library/products/{productId}/download`

```json
{
  "downloadUrl": "https://...",
  "downloadFileName": "material.pdf"
}
```

Requiere entitlement activo y registra `material_downloaded`.

## Errores comunes

```json
{"error": "mensaje"}
```

Estados relevantes: `400`, `401`, `403`, `404`, `409`, `429`, `502`, `503`.

## TypeScript mínimo

```ts
const API_URL = process.env.NEXT_PUBLIC_API_URL!;

export async function api(path: string, init: RequestInit = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error ?? "Error de API");
  return body;
}
```

No establecer manualmente `Content-Type` al enviar `FormData`.

## Retrofit mínimo

```kotlin
interface PaolaApi {
    @GET("auth/me") suspend fun me(): MeResponse
    @PATCH("auth/change-password") suspend fun changePassword(@Body body: ChangePasswordBody): ApiOk
    @Multipart @PATCH("auth/avatar") suspend fun uploadAvatar(@Part avatar: MultipartBody.Part): AvatarResponse
    @DELETE("auth/avatar") suspend fun deleteAvatar(): DeleteAvatarResponse
    @GET("orders/{id}/status") suspend fun orderStatus(@Path("id") id: String): OrderStatusResponse
    @GET("library") suspend fun library(): LibraryResponse
}
```

El interceptor Android agrega `Authorization: Bearer` y, tras cambiar contraseña, elimina el token local.
