# Pagos y Webhooks

## Flujo

1. El usuario autenticado envía productos y cantidades.
2. El backend obtiene productos y precios desde PostgreSQL.
3. Crea `Order` y `OrderItem` locales.
4. Crea la preference con `external_reference=order.id`.
5. Mercado Pago notifica `/api/payments/webhook`.
6. El backend exige firma en producción y consulta el pago real.
7. Valida orden, importe, moneda y preference.
8. Actualiza `Payment` sin bloquear cambios posteriores de `pending` a `approved`.
9. Usa `PaymentEvent` para deduplicar cada notificación, no todo el ciclo de vida del pago.
10. En una transacción bloquea la orden, completa acceso y registra eventos.
11. Después de confirmar datos, entrega biblioteca y envía el email registrado en `Notification`.

## Idempotencia

- `Payment.provider_payment_id` es único y se actualiza cuando cambia el estado.
- `PaymentEvent(provider, provider_event_id)` es único cuando existe un ID de evento.
- `PurchasedProduct` mantiene un único acceso activo por usuario/producto.
- Una notificación repetida no duplica email ni acceso.

## Reintentos

Un error temporal al consultar Mercado Pago devuelve `503`, permitiendo que el proveedor reintente. Errores permanentes de integridad —importe, moneda, reference o preference— se registran y no conceden acceso.

## Retornos

El backend nunca crea una preference sin `back_urls`. Si Mercado Pago las rechaza, la creación falla de forma visible y la orden queda marcada como fallida.

Las URLs de retorno mejoran la experiencia, pero no aprueban pagos. La única fuente de verdad es el pago consultado por el webhook y el endpoint autenticado de estado de orden.
