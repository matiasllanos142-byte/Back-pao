# Mercado Pago en produccion

Variables necesarias en Railway para el backend:

```env
MP_ACCESS_TOKEN=APP_USR-...
MP_WEBHOOK_SECRET=...
FRONTEND_URL=https://workenginecorp.com.ar
BACKEND_PUBLIC_URL=https://back-paopsicope-production.up.railway.app
CORS_ALLOWED_ORIGINS=https://workenginecorp.com.ar,https://www.workenginecorp.com.ar
```

En Mercado Pago, configurar Webhooks para el evento `payment` apuntando a:

```text
https://back-paopsicope-production.up.railway.app/api/payments/webhook
```

El backend tambien envia `notification_url` al crear cada preferencia:

```text
https://back-paopsicope-production.up.railway.app/api/payments/webhook?source_news=webhooks
```

Codex MCP de Mercado Pago, cuando tengas el Access Token:

```toml
[mcp_servers.mercadopago-mcp-server]
command = "npx"
args = [
  "-y",
  "mcp-remote",
  "https://mcp.mercadopago.com/mcp",
  "--header",
  "Authorization:${AUTH_HEADER}"
]

[mcp_servers.mercadopago-mcp-server.env]
AUTH_HEADER = "Bearer APP_USR-..."
```

Sin `MP_ACCESS_TOKEN`, la tienda queda en modo demo y libera la compra sin Mercado Pago. En produccion esa variable tiene que existir.
