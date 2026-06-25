# Railway, Postgres y compras de usuarios

## Necesito Redis?

No para este flujo.

Postgres alcanza para:

- usuarios registrados
- productos
- ordenes
- items comprados
- accesos de descarga por usuario

Redis seria util mas adelante para colas, cache, tareas en background o rate
limiting, pero no hace falta para guardar compras ni sesiones actuales.

## Como enganchar Postgres con Django

El backend ya lee la variable:

```text
DATABASE_URL
```

En Railway, el servicio `Back-Paopsicope` tiene que tener una variable
compartida o referenciada al Postgres del proyecto. En Variables, usa
`Add Variable` y elegi la variable del servicio Postgres, normalmente:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

El nombre exacto del servicio puede variar en Railway. Lo importante es que el
backend tenga `DATABASE_URL` apuntando al Postgres online.

## Migraciones

El `Procfile` corre migraciones antes de arrancar:

```text
python manage.py migrate && gunicorn ...
```

Eso crea/actualiza tablas como:

- `users`
- `orders`
- `order_items`
- `products`
- `purchased_products`

## Flujo de compra

1. El cliente se registra o inicia sesion.
2. El checkout exige sesion.
3. El backend crea la orden con `user_id`.
4. Si Mercado Pago aprueba, la orden pasa a `completada`.
5. El backend crea registros en `purchased_products`.
6. `/api/library` devuelve los productos comprados del usuario.
7. `/api/library/products/<product_id>/download` devuelve la URL de descarga si el usuario compro ese producto.

## Variables de Railway que importan

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=una-clave-larga-y-segura
DEBUG=False
ALLOWED_HOSTS=back-paopsicope-production.up.railway.app
CORS_ALLOWED_ORIGINS=https://tu-front.vercel.app
FRONTEND_URL=https://tu-front.vercel.app
AUTH_COOKIE_SAMESITE=None
AUTH_COOKIE_SECURE=True
MP_ACCESS_TOKEN=APP_USR_xxxxxxxxx
```

Cloudinary para imagenes y archivos:

```text
CLOUDINARY_CLOUD_NAME=xxxx
CLOUDINARY_API_KEY=xxxx
CLOUDINARY_API_SECRET=xxxx
CLOUDINARY_UPLOAD_FOLDER=paola-psicope/products
CLOUDINARY_MAX_UPLOAD_BYTES=5242880
CLOUDINARY_DOWNLOAD_FOLDER=paola-psicope/downloads
CLOUDINARY_MAX_DOWNLOAD_BYTES=26214400
```

Resend:

```text
RESEND_API_KEY=re_xxxxxxxxx
RESEND_FROM_EMAIL=Paola Psicope <no-reply@mail.tu-dominio.com>
RESEND_REPLY_TO=contacto@tu-dominio.com
RESEND_TIMEOUT_SECONDS=15
BACKEND_PUBLIC_URL=https://back-paopsicope-production.up.railway.app
EMAIL_VERIFICATION_TOKEN_TTL_SECONDS=86400
EMAIL_VERIFICATION_SUCCESS_URL=https://tu-front.vercel.app/login?verified=1
EMAIL_VERIFICATION_ERROR_URL=https://tu-front.vercel.app/login?verified=0
```

## Variables de Vercel

El frontend no lleva credenciales privadas de SQL, Resend, Cloudinary ni Mercado
Pago.

Solo necesita saber donde esta el backend:

```text
NEXT_PUBLIC_API_URL=https://back-paopsicope-production.up.railway.app
```

Nada de `DATABASE_URL` en Vercel.
Nada de `RESEND_API_KEY` en Vercel.
Nada de `CLOUDINARY_API_SECRET` en Vercel.
Nada de `MP_ACCESS_TOKEN` en Vercel.
