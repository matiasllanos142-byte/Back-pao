# ADMIN ANDROID BACKEND CONTRACT

## Stack

| Component | Version |
|---|---|
| Django | 6.0.6 |
| Django REST Framework | 3.17.1 |
| djangorestframework-simplejwt | 5.5.1 |
| PyJWT | 2.13.0 |
| Python | 3.14.3 |
| Database | PostgreSQL (via dj-database-url) |
| Image storage | Cloudinary |
| File storage | Cloudflare R2 (S3-compatible) |
| AI | NVIDIA API |
| Payments | Mercado Pago SDK 3.2.0 |
| Email | Resend |

## Commit Base

```
c54d2266fad388e51cdc8a8b3e7bfd2cded260d1
```

## Files Modified

| File | Change |
|---|---|
| `api/views.py` | Improved login, /me, logout; added dashboard, order detail, files, settings |
| `api/urls.py` | Added routes for dashboard, order detail, files, settings |
| `api/serializers.py` | No changes needed |
| `api/tests.py` | Added 27 new tests for Android admin API |

## Endpoints Conserved (unchanged)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/admin/login` | Improved response, same request |
| POST | `/api/admin/logout` | Same behavior, response changed to `{"success": true}` |
| GET | `/api/admin/me` | Improved response with full admin data |
| GET | `/api/admin/dashboard/stats` | Unchanged |
| GET/POST | `/api/admin/products` | Unchanged |
| GET/PUT/PATCH/DELETE | `/api/admin/products/{id}` | Unchanged, soft-delete |
| GET | `/api/admin/orders` | Unchanged |
| POST | `/api/admin/uploads/image` | Unchanged |
| POST | `/api/admin/uploads/download` | Unchanged |
| GET/POST | `/api/admin/workbooks` | Unchanged |
| POST | `/api/admin/workbooks/chat` | Unchanged |
| POST | `/api/admin/workbooks/{id}/build` | Unchanged |
| GET | `/api/admin/workbooks/{id}/pdf` | Unchanged |

## Endpoints Added

| Method | Path | Handler | Auth |
|---|---|---|---|
| GET | `/api/admin/dashboard` | `admin_dashboard_view` | IsEnvAdmin |
| GET | `/api/admin/orders/{id}` | `admin_order_detail_view` | IsEnvAdmin |
| GET | `/api/admin/files` | `admin_files_view` | IsEnvAdmin |
| GET | `/api/admin/settings` | `admin_settings_view` | IsEnvAdmin |

## Endpoints Not Implemented (documented as out of scope)

- Refresh token
- Token blacklist
- Admin registration
- Health check
- Category CRUD
- Activity log
- Refunds
- Manual payment editing
- Library admin

## Models Used

| Model | File | Usage |
|---|---|---|
| User | `api/models.py:7` | Admin data resolution |
| Product | `api/models.py:254` | List, create, update, soft-delete, file derivation |
| Order | `api/models.py:389` | List, detail |
| OrderItem | `api/models.py:420` | Order items |
| Payment | `api/models.py:53` | Order payment info |
| UserEvent | `api/models.py:148` | Download count |
| WorkbookDraft | `api/models.py:330` | Workbook list + PDF |
| Category | `api/models.py:239` | Product categories |
| CloudinarySettings | `api/models.py:288` | Settings status |
| NvidiaSettings | `api/models.py:305` | Settings status |

## Serializers Used

| Serializer | File | Usage |
|---|---|---|
| OrderSerializer | `api/serializers.py:323` | Order list + detail |
| ProductSerializer | `api/serializers.py:193` | Product create/update |
| ProductListSerializer | `api/serializers.py:253` | Product list |

## Authentication

- **Public auth (users)**: SimpleJWT with `JWTCookieAuthentication` (cookie `session` + Bearer)
- **Admin auth**: Custom JWT using PyJWT, stored in cookie `admin_session` + Bearer
- **Admin permission**: `IsEnvAdmin` class checks admin JWT via `get_admin_from_request()`
- **Token payload**: `{"sub": email, "role": "admin", "iat": ..., "exp": ...}`
- **Token expiry**: 24 hours (configurable via `ADMIN_TOKEN_TTL`)
- **Signing**: HMAC-SHA256 with `ADMIN_JWT_SECRET` (default: `SECRET_KEY`)

## Key Permissions

- `AllowAny` — login, logout, me (admin auth is self-validating)
- `IsEnvAdmin` — all protected admin endpoints
- `IsAuthenticated` — public user endpoints (library, orders, payments)

## Retained Backward Compatibility

- Login response still includes `adminToken`, `token`, `accessToken` fields
- Login response `admin.username` is the raw input (preserving existing web dashboard behavior)
- Admin cookie `admin_session` is still set on login
- `/me` still accepts cookie-based auth
- `admin_dashboard_stats_view` kept intact alongside new `admin_dashboard_view`
- Product CRUD, uploads, workbooks, orders list unchanged
- `/admin/orders` list still returns flat array (not paginated object)

## Tests

| Suite | Tests | Status |
|---|---|---|
| `AdminAuthTests` (original) | 35 | All pass |
| `AdminAuthTests` (new) | 27 | All pass |
| `RefactorAuthAvatarAdminTests` | 12 | 5 pre-existing failures (unrelated: 301 redirect on login, mocked Cloudinary/NVIDIA availability) |

New tests cover:
- Login with structured admin response
- Login validation (empty username/password)
- Logout returns success JSON
- `/me` with Bearer returns full data
- `/me` without token returns 401
- `/me` with user token returns 401
- Dashboard requires admin
- Dashboard returns expected structure
- Dashboard downloadsCount is nullable
- Products list with Bearer
- Product create and update
- Product soft-delete
- Orders list
- Order detail with Bearer
- Order detail 404
- Order detail requires admin
- Order list preserves contract
- Files derive from products
- Files null fields
- Files requires admin
- Settings requires admin
- Settings read-only structure
- Settings no secrets exposed
- Settings PUT not allowed
- Workbooks list requires admin
- Workbooks create with mocked external services

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| No refresh token | Client must re-login every 24h | Documented in contract |
| No token revocation | Token usable until expiry | Client-side deletion documented |
| No rate limit on login | Brute force possible | Future P2 enhancement |
| Env-var admin lacks DB record | `id` is `null` in responses | Android handles nullable id |
| Fallback admin in DEBUG | Hardcoded credentials in source | Disabled by default, only in DEBUG |
| Pre-existing test failures | 5 refactor tests fail with 301 | Unrelated to this contract |

## Retrofit Kotlin Example

```kotlin
interface PaolaAdminApi {
    @POST("api/admin/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @GET("api/admin/me")
    suspend fun me(): AdminMeResponse

    @POST("api/admin/logout")
    suspend fun logout(): LogoutResponse

    @GET("api/admin/dashboard")
    suspend fun dashboard(): DashboardResponse

    @GET("api/admin/products")
    suspend fun listProducts(): List<ProductResponse>

    @POST("api/admin/products")
    suspend fun createProduct(@Body body: ProductRequest): ProductResponse

    @Multipart
    @POST("api/admin/uploads/image")
    suspend fun uploadImage(@Part image: MultipartBody.Part): UploadResponse

    @Multipart
    @POST("api/admin/uploads/download")
    suspend fun uploadDownload(@Part file: MultipartBody.Part): UploadResponse

    @GET("api/admin/orders")
    suspend fun listOrders(): OrdersListResponse

    @GET("api/admin/orders/{id}")
    suspend fun orderDetail(@Path("id") id: String): OrderDetailResponse

    @GET("api/admin/files")
    suspend fun listFiles(): FilesResponse

    @GET("api/admin/settings")
    suspend fun getSettings(): SettingsResponse
}
```

## Final Contract Table

| # | Method | Path | Auth | Android | Status |
|---|---|---|---|---|---|
| 1 | POST | `/api/admin/login` | None | Bearer + JSON | Adopted with enhancement |
| 2 | GET | `/api/admin/me` | Bearer | Bearer | Adopted with enhancement |
| 3 | POST | `/api/admin/logout` | Bearer | Bearer + local cleanup | Adopted |
| 4 | GET | `/api/admin/dashboard` | Bearer | Bearer | New |
| 5 | GET/POST | `/api/admin/products` | Bearer | Bearer | Adopted as-is |
| 6 | GET/PUT/PATCH/DELETE | `/api/admin/products/{id}` | Bearer | Bearer | Adopted as-is |
| 7 | POST | `/api/admin/uploads/image` | Bearer | Multipart | Adopted as-is |
| 8 | POST | `/api/admin/uploads/download` | Bearer | Multipart | Adopted as-is |
| 9 | GET | `/api/admin/orders` | Bearer | Bearer | Adopted as-is |
| 10 | GET | `/api/admin/orders/{id}` | Bearer | Bearer | New |
| 11 | GET | `/api/admin/files` | Bearer | Bearer | New (derived) |
| 12 | GET | `/api/admin/settings` | Bearer | Bearer | New (read-only) |
| 13 | GET/POST | `/api/admin/workbooks` | Bearer | Bearer | Adopted as-is |
| 14 | GET | `/api/admin/workbooks/{id}/pdf` | Bearer | Binary download | Adopted as-is |
