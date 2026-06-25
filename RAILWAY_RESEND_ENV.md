# Variables de Railway para Resend

Estas variables van en el backend de Railway, no en Vercel ni en el frontend.

## Paso 1: Resend

Antes de cargar variables, entra a Resend y verifica un dominio o subdominio
propio. Para produccion usa algo como `no-reply@paolapsicope.com` o
`no-reply@mail.paolapsicope.com`.

```text
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxx
RESEND_FROM_EMAIL=Paola Psicope <no-reply@tu-dominio.com>
RESEND_REPLY_TO=contacto@tu-dominio.com
RESEND_TIMEOUT_SECONDS=15
```

`RESEND_FROM_EMAIL` tiene que salir desde un dominio verificado en Resend.

## Paso 2: links de verificacion

```text
BACKEND_PUBLIC_URL=https://tu-backend.up.railway.app
EMAIL_VERIFICATION_TOKEN_TTL_SECONDS=86400
EMAIL_VERIFICATION_SUCCESS_URL=https://tu-frontend.vercel.app/login?verified=1
EMAIL_VERIFICATION_ERROR_URL=https://tu-frontend.vercel.app/login?verified=0
```

`BACKEND_PUBLIC_URL` debe ser la URL publica del backend en Railway. El link
que llega por email apunta a:

```text
https://tu-backend.up.railway.app/api/auth/verify-email?token=...
```

## Paso 3: CLI de Railway

Desde la carpeta del backend, con el proyecto de Railway vinculado:

```powershell
railway link
railway variables --set "RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxx"
railway variables --set "RESEND_FROM_EMAIL=Paola Psicope <no-reply@tu-dominio.com>"
railway variables --set "RESEND_REPLY_TO=contacto@tu-dominio.com"
railway variables --set "RESEND_TIMEOUT_SECONDS=15"
railway variables --set "BACKEND_PUBLIC_URL=https://tu-backend.up.railway.app"
railway variables --set "EMAIL_VERIFICATION_TOKEN_TTL_SECONDS=86400"
railway variables --set "EMAIL_VERIFICATION_SUCCESS_URL=https://tu-frontend.vercel.app/login?verified=1"
railway variables --set "EMAIL_VERIFICATION_ERROR_URL=https://tu-frontend.vercel.app/login?verified=0"
```

## Variables relacionadas que ya deberia tener Railway

```text
SECRET_KEY=una-clave-larga-y-segura
DEBUG=False
ALLOWED_HOSTS=tu-backend.up.railway.app
CORS_ALLOWED_ORIGINS=https://tu-frontend.vercel.app
FRONTEND_URL=https://tu-frontend.vercel.app
AUTH_COOKIE_SAMESITE=None
AUTH_COOKIE_SECURE=True
```

## Que hace el backend

- Cuando alguien se registra, el backend crea el usuario y manda un email de
  verificacion por Resend.
- El token del link esta firmado por Django y expira segun
  `EMAIL_VERIFICATION_TOKEN_TTL_SECONDS`.
- Cuando la persona abre el link, el backend marca `email_verified=True`.
- Si `RESEND_API_KEY` todavia no esta configurada, el registro no se rompe:
  crea el usuario y responde `emailVerificationSent=false`.
- Las credenciales de Resend nunca se usan en el frontend.
