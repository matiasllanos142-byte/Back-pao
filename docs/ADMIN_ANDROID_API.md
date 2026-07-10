# Paola Admin — Android API Contract

## Base URL

All endpoints are relative to the backend base URL:

```
https://<backend>/api/
```

## Authentication

All admin endpoints require `Authorization: Bearer <token>` obtained from login.

### POST `/api/admin/login`

Authenticate as admin. Accepts `username` or `email`.

**Request**:
```json
{
  "username": "admin",
  "password": "secreto123"
}
```

**Response 200**:
```json
{
  "accessToken": "eyJ...",
  "adminToken": "eyJ...",
  "token": "eyJ...",
  "admin": {
    "username": "admin",
    "id": "uuid-optional",
    "name": "Admin Name",
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

**Response 400** (empty credentials):
```json
{
  "error": "ADMIN_UNAUTHORIZED",
  "message": "Usuario y contrasena son obligatorios.",
  "details": null
}
```

**Response 401** (invalid credentials):
```json
{
  "error": "ADMIN_UNAUTHORIZED",
  "message": "Credenciales de administracion incorrectas.",
  "details": null
}
```

Notes:
- `id` can be `null` when the admin is configured via environment variables (not a database user)
- Cookie `admin_session` is also set (for web dashboard compatibility), but Android must use `Authorization: Bearer`
- The returned `accessToken`, `adminToken`, and `token` fields all contain the same JWT

### GET `/api/admin/me`

Get current admin identity. Must include `Authorization: Bearer <token>`.

**Response 200**:
```json
{
  "admin": {
    "username": "admin@example.com",
    "id": "uuid",
    "name": "Admin Name",
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

**Response 401**:
```json
{
  "error": "ADMIN_UNAUTHORIZED",
  "message": "No se pudo autenticar la solicitud.",
  "details": null
}
```

### POST `/api/admin/logout`

Invalidates the session cookie. Does NOT invalidate the JWT token.

**Response 200**:
```json
{
  "success": true
}
```

**Limitation**: The JWT token remains valid until it expires (default 24 hours). The Android client must delete the token locally. Token revocation (blacklist) is not implemented.

## Dashboard

### GET `/api/admin/dashboard`

Requires `Authorization: Bearer <token>`.

**Response 200**:
```json
{
  "salesThisMonth": "45000.00",
  "ordersCount": 120,
  "productsCount": 15,
  "downloadsCount": null,
  "salesTrend": [],
  "recentOrders": [
    {
      "id": "uuid",
      "customerName": "Juan Perez",
      "total": "3500.00",
      "status": "completada",
      "createdAt": "2026-07-10T12:00:00Z"
    }
  ],
  "recentProducts": [
    {
      "id": "uuid",
      "title": "Producto X",
      "price": "1500.00",
      "image": "/images/products/placeholder.jpg",
      "isActive": true,
      "createdAt": "2026-07-10T12:00:00Z"
    }
  ]
}
```

Notes:
- `salesThisMonth`: sum of completed order totals for current month
- `downloadsCount`: event count, nullable (`null` when no download events exist)
- `salesTrend`: currently always `[]` (feature planned)
- `recentOrders`: last 5 orders
- `recentProducts`: last 5 active products

### GET `/api/admin/dashboard/stats` (existing, preserved)

Original detailed stats endpoint. See existing contract in the codebase.

## Products

### GET `/api/admin/products`

List products (all, active and inactive).

**Response 200**: Array of products (see detail response for field list).

### POST `/api/admin/products`

Create a product.

**Request**:
```json
{
  "title": "Nuevo Producto",
  "description": "Descripción detallada",
  "price": "2500.00",
  "compare_at_price": "3000.00",
  "category": "estimulacion",
  "badge": "Oferta",
  "featured": false,
  "age": "6-8",
  "level": "Inicial",
  "features": [],
  "objectives": []
}
```

**Response 201**: Created product object.

### GET `/api/admin/products/{id}`

Product detail.

### PUT/PATCH `/api/admin/products/{id}`

Update a product. PUT for full update, PATCH for partial.

### DELETE `/api/admin/products/{id}`

Soft-deletes a product (sets `is_active = false`). Does NOT remove from database.

**Response 204**: No content (soft-delete successful).

### Product fields

| Field | Type | Nullable | Notes |
|---|---|---|---|
| id | string (UUID) | No | |
| title | string | No | |
| description | string | No | |
| price | string (decimal) | No | |
| compare_at_price | string (decimal) | Yes | |
| category | string (slug) | No | Auto-creates categories |
| image | string (URL) | No | Cloudinary URL |
| image_public_id | string | Yes | |
| download_url | string (URL) | Yes | R2 public URL |
| download_filename | string | Yes | |
| download_public_id | string | Yes | R2 object key |
| download_content_type | string | Yes | MIME type |
| download_size | number | Yes | Bytes |
| badge | string | Yes | |
| featured | boolean | No | |
| age | string | No | |
| level | string | No | |
| features | array | No | |
| objectives | array | No | |
| metadata | object | No | |
| is_active | boolean | No | |
| created_at | string (ISO 8601) | No | |

## Uploads

### POST `/api/admin/uploads/image`

Upload an image to Cloudinary.

**Request**: `multipart/form-data`
- Field: `image` (file)
- Accepted: image types (JPEG, PNG, WebP, GIF, etc.)
- Max size: configured by `CLOUDINARY_MAX_UPLOAD_BYTES` (default 5 MB)

**Response 200**:
```json
{
  "url": "https://res.cloudinary.com/...",
  "publicId": "paola-psicope/products/...",
  "contentType": "image/jpeg",
  "bytes": 50000,
  "resourceType": "image",
  "format": "jpg"
}
```

### POST `/api/admin/uploads/download`

Upload a PDF/ZIP file to Cloudflare R2.

**Request**: `multipart/form-data`
- Field: `file` (file)
- Accepted: PDF (.pdf), ZIP (.zip)
- Max size: configured by `DOWNLOAD_MAX_BYTES` (default 100 MB)

**Response 200**:
```json
{
  "url": "https://r2-bucket/...",
  "fileName": "cuadernillo.pdf",
  "objectKey": "paola-psicope/products/downloads/uuid-file.pdf",
  "publicId": "paola-psicope/products/downloads/uuid-file.pdf",
  "contentType": "application/pdf",
  "bytes": 1500000,
  "storage": "r2"
}
```

## Orders

### GET `/api/admin/orders`

List orders (latest 100, no pagination).

**Response 200**:
```json
{
  "orders": [
    {
      "id": "uuid",
      "total": "3500.00",
      "status": "completada|pendiente|fallida|reembolsada",
      "preference_id": "12345",
      "payment_id": "67890",
      "external_reference": "order-uuid",
      "customer": {
        "name": "Juan",
        "email": "juan@mail.com"
      },
      "items": [
        {
          "product": {
            "id": "uuid",
            "title": "Producto",
            "price": "1500.00",
            "category": "estimulacion",
            "image": "...",
            "badge": null,
            "featured": false,
            "age": "6-8",
            "level": "Inicial",
            "features": [],
            "objectives": [],
            "created_at": "...",
            "galleryImages": []
          },
          "quantity": 1,
          "price": "1500.00"
        }
      ],
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

### GET `/api/admin/orders/{id}`

Order detail with payment info.

**Response 200**: Same structure as list item, plus:
```json
{
  "paymentId": "mp-payment-id",
  "preferenceId": "mp-preference-id",
  "externalReference": "order-uuid"
}
```

## Files (derived from products)

### GET `/api/admin/files`

List downloadable files derived from products with non-empty `download_url`.

**Response 200**:
```json
{
  "items": [
    {
      "id": "product-uuid",
      "productId": "product-uuid",
      "productTitle": "Cuadernillo de Estimulación",
      "fileName": "cuadernillo.pdf",
      "fileType": "pdf",
      "mimeType": "application/pdf",
      "size": 1500000,
      "url": "https://r2-bucket/...",
      "createdAt": "2026-01-01T00:00:00Z"
    }
  ]
}
```

Notes:
- `fileType`: derived from MIME type — `"pdf"`, `"zip"`, or `null`
- Fields are `null` when the corresponding product field is empty
- URLs are public R2 URLs (no signature required)

## Settings (read-only)

### GET `/api/admin/settings`

Technical settings overview. Read-only.

**Response 200**:
```json
{
  "cloudinary": {
    "configured": true,
    "cloudName": "my-cloud"
  },
  "nvidia": {
    "configured": true,
    "model": "meta/llama-3.1-8b-instruct"
  },
  "storage": {
    "configured": true,
    "provider": "r2"
  }
}
```

- `cloudName` and `model` may be `null` if unconfigured
- No API keys, secrets, tokens, or passwords are ever returned
- `PUT` is not supported (405 Method Not Allowed)

## Workbooks (Cuadernillos IA)

### GET `/api/admin/workbooks`

List workbook drafts (latest 20).

### POST `/api/admin/workbooks`

Create a workbook draft from a plan.

### POST `/api/admin/workbooks/chat`

Chat-based workbook creation (sync, may take several seconds).

### POST `/api/admin/workbooks/{id}/build`

Build final content (sync, may take several seconds).

### GET `/api/admin/workbooks/{id}/pdf`

Download generated PDF. Returns `application/pdf` binary.

Notes:
- All workbook operations are synchronous
- No queuing, no polling, no progress percentage
- Status values: `planned`, `building`, `done`, `error`
- External NVIDIA API calls are mocked in test environments

## Error Format

All errors follow this normalized format (on new/modified endpoints):

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description.",
  "details": null
}
```

| HTTP Status | Error Code | When |
|---|---|---|
| 400 | `ADMIN_UNAUTHORIZED` | Missing or empty credentials |
| 401 | `ADMIN_UNAUTHORIZED` | Missing, invalid, or expired token |
| 403 | (varies) | Authenticated but not admin |
| 404 | (varies) | Resource not found |
| 405 | (varies) | Method not allowed |
| 500 | (varies) | Internal server error |

## Endpoints NOT Implemented

The following will NOT be implemented (not needed or covered by existing functionality):

- Refresh token (admin JWT has no refresh mechanism)
- Token blacklist/revocation
- Admin registration
- Health check
- Category CRUD
- Activity log
- Refunds
- Manual payment editing
- Library admin
- Turnos/shifts admin
- Physical product deletion (soft-delete only)

## Retrofit Compatibility

All endpoints are compatible with Retrofit/OkHttp:

- `Authorization: Bearer <token>` via OkHttp Interceptor
- JSON via `@Body` or `@Field`
- Multipart via `@Multipart` with exact field names: `image`, `file`
- No cookie dependency
- No CSRF tokens
- No HTML responses
- No redirects
- ISO 8601 date format

## Risks

| Risk | Description |
|---|---|
| Token expiry | Admin JWT expires after 24h; no refresh mechanism; client must re-login |
| No token revocation | Logout does not invalidate token; token usable until expiry |
| No rate limiting | Login endpoint has no throttle; susceptible to brute force |
| Env-var admin lacks ID | Admin configured via env vars has `id: null` in responses |
| Fallback admin in DEBUG | Built-in fallback admin only enabled when `ALLOW_BUILTIN_ADMIN_FALLBACK=True` and `DEBUG=True` |
