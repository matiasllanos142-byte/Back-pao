# Variables de Railway — Paola Psicopé Backend

Este documento enumera nombres y formatos. No contiene credenciales reales.

## URLs y Django

| Variable | Obligatoria | Ejemplo ficticio | Uso |
|---|---:|---|---|
| `SECRET_KEY` | Sí | `<random-64-plus-chars>` | Firma Django y JWT de usuarios. Generar un valor criptográficamente aleatorio. |
| `DEBUG` | Sí | `False` | Debe ser `False` en producción. |
| `ALLOWED_HOSTS` | Sí | `backend.example.com` | Hosts aceptados por Django, separados por coma. |
| `DATABASE_URL` | Sí | `postgresql://USER:PASSWORD@HOST:PORT/DB` | PostgreSQL provisto por Railway. No copiarlo al frontend. |
| `BACKEND_PUBLIC_URL` | Sí | `https://backend.example.com` | URL pública HTTPS del servicio Railway, sin `/api` y sin barra final. |
| `FRONTEND_URL` | Sí | `https://www.example.com` | Dominio web canónico usado por retornos de Mercado Pago y emails. Usar un solo dominio. |
| `CORS_ALLOWED_ORIGINS` | Sí | `https://www.example.com` | Orígenes web permitidos, separados por coma. No usar `*` con credenciales. |
| `AUTH_COOKIE_SECURE` | Sí | `True` | Cookies solo por HTTPS. |
| `AUTH_COOKIE_SAMESITE` | Sí | `None` | Necesario cuando Vercel y Railway usan dominios distintos. |
| `SECURE_SSL_REDIRECT` | Sí | `True` | Fuerza HTTPS. |

## Mercado Pago

| Variable | Obligatoria | Ejemplo ficticio | Uso |
|---|---:|---|---|
| `MP_ACCESS_TOKEN` | Sí | `<APP_USR_ACCESS_TOKEN>` | Access Token productivo de la aplicación vendedora. Solo backend. |
| `MP_WEBHOOK_SECRET` | Sí | `<webhook-signature-secret>` | Clave secreta generada en Mercado Pago para validar `x-signature`. |
| `MP_MODE` | Sí | `production` | Valores: `production`, `test` o `auto`. En Railway usar `production`. |
| `MP_ALLOW_UNSIGNED_WEBHOOKS_IN_DEBUG` | No | `False` | Solo desarrollo local. Nunca activar en Railway. |

Webhook público derivado por el backend:

```text
${BACKEND_PUBLIC_URL}/api/payments/webhook?source_news=webhooks
```

Configurar esa misma URL en Mercado Pago → Tu integración → Webhooks → Pagos. No existe una variable separada para el endpoint.

## Resend

| Variable | Obligatoria | Ejemplo ficticio | Uso |
|---|---:|---|---|
| `RESEND_API_KEY` | Sí | `<re_xxx>` | API key de Resend. Solo backend. |
| `RESEND_FROM_EMAIL` | Sí | `Paola Psicopé <noreply@example.com>` | Remitente perteneciente a un dominio verificado. |
| `RESEND_REPLY_TO` | No | `soporte@example.com` | Dirección de respuesta. |
| `RESEND_TIMEOUT_SECONDS` | No | `15` | Timeout de solicitudes. Debe quedar por debajo del timeout del webhook. |
| `EMAIL_ASSETS_BASE_URL` | Sí | `https://backend.example.com/static/email` | Base pública para imágenes de emails. |
| `EMAIL_VERIFICATION_SUCCESS_URL` | No | `https://www.example.com/verificacion-exitosa` | Retorno web tras verificar email. |
| `EMAIL_VERIFICATION_ERROR_URL` | No | `https://www.example.com/verificacion-error` | Retorno web ante token inválido. |

## Cloudinary y avatar

| Variable | Obligatoria | Ejemplo ficticio | Uso |
|---|---:|---|---|
| `CLOUDINARY_CLOUD_NAME` | Sí | `<cloud-name>` | Cuenta Cloudinary. |
| `CLOUDINARY_API_KEY` | Sí | `<api-key>` | API key de Cloudinary. Solo backend. |
| `CLOUDINARY_API_SECRET` | Sí | `<api-secret>` | API secret. Solo backend. |
| `CLOUDINARY_SETTINGS_SECRET` | Sí | `<independent-random-secret>` | Protege configuración guardada. No reutilizar una clave pública. |
| `CLOUDINARY_UPLOAD_FOLDER` | No | `paola-psicope/products` | Carpeta de imágenes de productos. |
| `CLOUDINARY_AVATAR_FOLDER` | No | `paola-psicope/avatars` | Carpeta raíz; el backend agrega el UUID del usuario. |
| `CLOUDINARY_AVATAR_MAX_BYTES` | No | `5242880` | Máximo del avatar, en bytes. |

## Administración

La opción recomendada es un usuario PostgreSQL con `is_admin=True`.

| Variable | Obligatoria | Ejemplo ficticio | Uso |
|---|---:|---|---|
| `ADMIN_USERNAME` | Transición | `admin@example.com` | Login administrativo ambiental existente. |
| `ADMIN_PASSWORD_HASH` | Transición | `<django-pbkdf2-hash>` | Hash Django, nunca contraseña en texto plano. |
| `ADMIN_JWT_SECRET` | Sí mientras exista admin ambiental | `<independent-random-secret>` | Firma de tokens admin. |
| `ADMIN_TOKEN_TTL` | No | `86400` | Duración en segundos. |
| `ALLOW_BUILTIN_ADMIN_FALLBACK` | Sí | `False` | Debe ser `False` en producción. El fallback solo puede operar además con `DEBUG=True`. |

## R2 y cuadernillos

Conservar las variables actuales si el sistema sigue descargando materiales desde R2:

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_PUBLIC_BASE_URL
R2_DOWNLOAD_PREFIX
DOWNLOAD_MAX_BYTES
```

Conservar también las variables NVIDIA actuales si continúa activo el generador de cuadernillos.

## Variables públicas para clientes

El frontend y Android solamente necesitan conocer la URL base pública:

```text
NEXT_PUBLIC_API_URL=https://backend.example.com/api
ANDROID_API_BASE_URL=https://backend.example.com/api/
```

No exponer en web ni Android ninguna credencial de Mercado Pago, PostgreSQL, Resend, Cloudinary o administración.

## Distribución de la aplicación Android

| Variable | Obligatoria | Ejemplo | Uso |
|---|---:|---|---|
| `GITHUB_OWNER` | Sí | `negro123454332-jpg` | Propietario fijo del repositorio Android. |
| `GITHUB_REPO` | Sí | `app-pao` | Repositorio fijo con Releases. |
| `GITHUB_TOKEN` | Solo repositorio privado | `<fine-grained-pat>` | Token exclusivo de backend con permiso Contents: read. |
| `GITHUB_APK_ASSET_NAME` | Sí | `paola-psicope.apk` | Nombre exacto del asset APK. |
| `GITHUB_SHA256_ASSET_NAME` | No | `paola-psicope.apk.sha256` | Checksum opcional. |
| `GITHUB_RELEASE_CACHE_TTL_SECONDS` | No | `300` | Caché de metadata por instancia. |
| `GITHUB_CONNECT_TIMEOUT_SECONDS` | No | `5` | Timeout de conexión. |
| `GITHUB_READ_TIMEOUT_SECONDS` | No | `30` | Timeout de lectura remota. |

El token nunca se entrega a web o Android.
