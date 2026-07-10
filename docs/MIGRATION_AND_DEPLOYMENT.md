# Migración y despliegue seguro

## Antes de producción

En la rama local:

```powershell
python manage.py makemigrations --check
python manage.py migrate --plan
python manage.py check
python manage.py test api --verbosity=2
```

No continuar si aparece una migración adicional no explicada o falla un test.

## Orden de producción

1. Crear backup verificable de PostgreSQL.
2. Confirmar variables de `docs/RAILWAY_VARIABLES.md`.
3. Confirmar que `DEBUG=False`.
4. Confirmar `ALLOW_BUILTIN_ADMIN_FALLBACK=False`.
5. Confirmar `MP_ALLOW_UNSIGNED_WEBHOOKS_IN_DEBUG=False`.
6. Configurar en Mercado Pago el webhook HTTPS productivo.
7. Desplegar código.
8. Ejecutar migraciones `0013` mediante el proceso Railway actual.
9. Revisar logs de migración y health del servicio.
10. Simular un webhook firmado desde el panel de Mercado Pago.
11. Hacer una compra controlada de bajo importe.
12. Confirmar `Order`, `Payment`, `PaymentEvent`, biblioteca y `Notification`.
13. Confirmar retorno web, polling y vaciado del carrito.
14. Confirmar el email en Resend y en el dashboard admin.

## Reversión

No revertir la migración después de empezar a escribir pagos o notificaciones nuevas. Si el código falla, volver temporalmente al deploy anterior conservando las tablas nuevas y corregir hacia adelante. Restaurar el backup únicamente ante corrupción comprobada y con una ventana de mantenimiento.

## Punto de control

No hacer push a `main` ni desplegar Railway hasta recibir:

- salida completa de tests;
- revisión del patch;
- autorización explícita del usuario.
