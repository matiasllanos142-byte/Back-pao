import html
from django.conf import settings

EMAIL_HERO_IMAGES = {
    "verify_account": "verify-account.png",
    "welcome": "welcome.png",
    "password_reset": "password-reset.png",
    "purchase_confirmed": "purchase-confirmed.png",
    "download_ready": "download-ready.png",
    "download_help": "download-help.png",
    "new_product": "new-product.png",
    "product_updated": "product-updated.png",
    "abandoned_cart": "abandoned-cart.png",
    "support_received": "support-received.png",
}

FULL_NAMES = {
    "verify_account": "Verificar cuenta",
    "welcome": "Bienvenida",
    "password_reset": "Restablecer contraseña",
    "purchase_confirmed": "Compra confirmada",
    "download_ready": "Descarga lista",
    "download_help": "Ayuda para descargar",
    "new_product": "Nuevo recurso",
    "product_updated": "Recurso actualizado",
    "abandoned_cart": "Carrito abandonado",
    "support_received": "Consulta recibida",
}


def _assets_base_url():
    return getattr(settings, "EMAIL_ASSETS_BASE_URL", "").rstrip("/")


def _frontend_url():
    return getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")


def _hero_url(template_key):
    filename = EMAIL_HERO_IMAGES.get(template_key)
    base = _assets_base_url()
    if not filename or not base:
        return ""
    return f"{base}/{filename}"


def _e(text):
    return html.escape(str(text or ""))


def _cta_button(url, label):
    if not url:
        return ""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">'
        f'<tr><td style="text-align:center;">'
        f'<a href="{_e(url)}" style="background:#ff4f9a;color:#ffffff;text-decoration:none;padding:14px 24px;border-radius:999px;font-weight:700;font-family:Helvetica,Arial,sans-serif;font-size:15px;display:inline-block;">{_e(label)}</a>'
        f'</td></tr></table>'
    )


def _card_block(inner_html):
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 22px;">'
        f'<tr><td style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:18px 20px;">'
        f'{inner_html}'
        f'</td></tr></table>'
    )


def _bullet_list(items):
    if not items:
        return ""
    lis = "".join(
        f'<tr><td style="padding:3px 0;color:#333333;font-family:Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;">'
        f'<span style="color:#ff4f9a;margin-right:8px;">&#x2022;</span>{_e(item)}'
        f'</td></tr>'
        for item in items
    )
    return f'<table role="presentation" cellpadding="0" cellspacing="0">{lis}</table>'


def _spacer(height=16):
    return f'<table role="presentation" cellpadding="0" cellspacing="0" style="height:{height}px;"><tr><td style="height:{height}px;"></td></tr></table>'


def _base_html(content_html, hero_url, preheader=""):
    if hero_url:
        hero_section = (
            f'<tr><td style="padding:0;">'
            f'<img src="{_e(hero_url)}" alt="" width="600" style="display:block;width:100%;max-width:600px;height:auto;border:0;font-family:Helvetica,Arial,sans-serif;font-size:14px;color:#64748b;">'
            f'</td></tr>'
        )
    else:
        hero_section = (
            '<tr><td style="background:linear-gradient(135deg,#dbeafe,#fff0f6);height:6px;font-size:1px;line-height:1px;">'
            '&nbsp;</td></tr>'
        )

    preheader_html = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;font-size:1px;line-height:1px;mso-hide:all;">'
        f'{_e(preheader)}</div>'
    ) if preheader else ""

    frontend_home = _frontend_url()

    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="es">\n'
        f'<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="X-UA-Compatible" content="IE=edge">'
        f'<title>Paola Psicopé</title></head>\n'
        f'<body style="margin:0;padding:0;background-color:#fff8fd;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">\n'
        f'{preheader_html}\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#fff8fd;">\n'
        f'<tr><td align="center" style="padding:24px 10px;">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">\n'
        f'<tr><td style="background:linear-gradient(135deg,#3f87ec,#9b7ae5);border-radius:16px 16px 0 0;padding:24px 28px;text-align:center;">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">\n'
        f'<tr><td style="text-align:center;">\n'
        f'<h1 style="margin:0;color:#ffffff;font-family:Helvetica,Arial,sans-serif;font-size:22px;font-weight:700;">Paola Psicopé</h1>\n'
        f'<p style="margin:4px 0 0;color:rgba(255,255,255,0.85);font-family:Helvetica,Arial,sans-serif;font-size:13px;">Pedagogía para todos</p>\n'
        f'</td></tr></table>\n'
        f'</td></tr>\n'
        f'{hero_section}\n'
        f'<tr><td style="background:#ffffff;border-radius:0 0 16px 16px;padding:32px 28px;">\n'
        f'{content_html}\n'
        f'</td></tr>\n'
        f'<tr><td style="padding:24px 28px;text-align:center;">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">\n'
        f'<tr><td style="text-align:center;">\n'
        f'<p style="margin:0 0 4px;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:13px;">Paola Psicopé &mdash; Pedagogía para todos</p>\n'
        f'<p style="margin:0;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:12px;">\n'
        f'<a href="mailto:contacto@paolapsicope.com" style="color:#ff4f9a;text-decoration:none;">contacto@paolapsicope.com</a>\n'
        f'</p>\n'
        f'<p style="margin:4px 0 0;color:#94a3b8;font-family:Helvetica,Arial,sans-serif;font-size:11px;">\n'
        f'<a href="{_e(frontend_home)}" style="color:#94a3b8;text-decoration:underline;">paolapsicope.com</a>\n'
        f'</p>\n'
        f'</td></tr></table>\n'
        f'</td></tr>\n'
        f'</table>\n'
        f'</td></tr>\n'
        f'</table>\n'
        f'</body>\n'
        f'</html>'
    )


def _body_html(context, heading, paragraphs, extra_block="", cta_html="", after_cta_block=""):
    name = _e(context.get("name", ""))
    paras = "".join(
        f'<p style="margin:0 0 14px;color:#333333;font-family:Helvetica,Arial,sans-serif;font-size:16px;line-height:1.6;">{p}</p>'
        for p in paragraphs
    )
    return (
        f'<h2 style="margin:0 0 16px;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:24px;font-weight:700;">{_e(heading)}</h2>\n'
        f'<p style="margin:0 0 14px;color:#333333;font-family:Helvetica,Arial,sans-serif;font-size:16px;line-height:1.6;">Hola {_e(name)},</p>\n'
        f'{paras}'
        f'{extra_block}'
        f'{cta_html}'
        f'{after_cta_block}'
    )


# ------- Individual HTML builders -------

def _verify_account_html(context):
    code = context.get("code", "")
    verify_url = context.get("verify_url", "")
    expires_minutes = context.get("expires_minutes", "10")
    extra = ""

    if code:
        extra += _card_block(
            f'<p style="margin:0;color:#1d4ed8;font-family:Helvetica,Arial,sans-serif;font-size:34px;font-weight:800;letter-spacing:8px;text-align:center;">{_e(code)}</p>'
        )

    if verify_url:
        extra += _cta_button(verify_url, "Ir a verificar")

    extra += _card_block(
        f'<p style="margin:0;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:14px;">'
        f'Este código vence en {_e(str(expires_minutes))} minutos. '
        f'Si no pediste crear esta cuenta, podés ignorar este email.</p>'
    )

    heading = "Verificá tu cuenta"
    paras = [
        "Ingresá el siguiente código para terminar de crear tu cuenta en Paola Psicopé:",
    ]

    return _body_html(context, heading, paras, extra_block=extra)


def _welcome_html(context):
    store_url = context.get("store_url", "")
    account_url = context.get("account_url", "")

    cta = ""
    if store_url:
        cta = _cta_button(store_url, "Explorar tienda")
    if account_url:
        cta += _cta_button(account_url, "Ir a mi cuenta")

    extra = _card_block(
        '<p style="margin:0;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:14px;">'
        'Desde tu cuenta podés acceder a todos tus recursos comprados, seguir tus descargas '
        'y recibir novedades pensadas para acompañar procesos de aprendizaje.</p>'
    )

    heading = "Bienvenida a Paola Psicopé"
    paras = [
        "Gracias por sumarte al espacio de Paola Psicopé. Estamos felices de tenerte en la comunidad.",
        "Acá vas a encontrar recursos psicopedagógicos diseñados para familias, docentes y profesionales "
        "que quieren acompañar el desarrollo infantil desde el respeto, el juego y la emoción.",
    ]
    return _body_html(context, heading, paras, extra_block=extra, cta_html=cta)


def _password_reset_html(context):
    code = context.get("code", "")
    reset_url = context.get("reset_url", "")
    extra = ""

    if code:
        extra += _card_block(
            f'<p style="margin:0;color:#1d4ed8;font-family:Helvetica,Arial,sans-serif;font-size:34px;font-weight:800;letter-spacing:8px;text-align:center;">{_e(code)}</p>'
        )

    if reset_url:
        extra += _cta_button(reset_url, "Restablecer acceso")

    extra += _card_block(
        '<p style="margin:0;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:14px;">'
        'Si no pediste restablecer tu contraseña, podés ignorar este email. '
        'Nadie va a poder acceder a tu cuenta sin este código.</p>'
    )

    heading = "Restablecé tu contraseña"
    paras = [
        "Recibimos una solicitud para cambiar la contraseña de tu cuenta en Paola Psicopé. "
        "Ingresá el siguiente código en la página de recuperación:",
    ]
    return _body_html(context, heading, paras, extra_block=extra)


def _purchase_confirmed_html(context):
    order_id = context.get("order_id", "")
    product_title = context.get("product_title", "")
    total = context.get("total", "")
    payment_status = context.get("payment_status", "")
    order_url = context.get("order_url", "")
    download_links = context.get("download_links", []) or []
    guest_checkout = bool(context.get("guest_checkout"))

    details = []
    if product_title:
        details.append(("Producto", product_title))
    if order_id:
        details.append(("Orden", order_id))
    if payment_status:
        details.append(("Estado", payment_status))
    if total:
        details.append(("Total", total))

    rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#333333;font-family:Helvetica,Arial,sans-serif;font-size:15px;border-bottom:1px solid #e2e8f0;">{_e(label)}</td>'
        f'<td style="padding:6px 12px;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;border-bottom:1px solid #e2e8f0;text-align:right;">{_e(value)}</td></tr>'
        for label, value in details
    )

    extra = _card_block(
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;">'
        f'{rows}</table>'
    )

    if download_links:
        cta = "".join(
            _cta_button(item.get("url", ""), f"Descargar {item.get('label') or 'material'}")
            for item in download_links
        )
    else:
        cta = _cta_button(order_url or _frontend_url() + "/perfil#biblioteca", "Ver detalle")

    heading = "Compra confirmada"
    paras = (
        [
            "Recibimos tu compra y ya está confirmada. Podés descargar los materiales desde los botones de este email.",
            "Guardá este mensaje: los enlaces son personales y estarán disponibles durante 30 días.",
        ]
        if guest_checkout
        else [
            "Recibimos tu compra y ya está confirmada. El recurso queda disponible en tu cuenta para que lo descargues cuando lo necesites.",
            "Por seguridad no adjuntamos archivos en este email. Las descargas se realizan desde tu cuenta.",
        ]
    )
    return _body_html(context, heading, paras, extra_block=extra, cta_html=cta)


def _download_ready_html(context):
    product_title = context.get("product_title", "")
    library_url = context.get("library_url", "")
    file_type = context.get("file_type", "")
    support_url = context.get("support_url", "")

    details = []
    if product_title:
        details.append(("Recurso", product_title))
    if file_type:
        details.append(("Tipo", file_type))

    rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#333333;font-family:Helvetica,Arial,sans-serif;font-size:15px;">{_e(label)}</td>'
        f'<td style="padding:6px 12px;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;text-align:right;">{_e(value)}</td></tr>'
        for label, value in details
    )

    extra = _card_block(
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;">{rows}</table>'
    )

    cta = _cta_button(library_url or _frontend_url() + "/perfil#biblioteca", "Ir a mis compras")

    after = ""
    if support_url:
        after = (
            f'<p style="margin:0;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:14px;">'
            f'Si tenés alguna duda, respondé este email o escribinos a '
            f'<a href="mailto:{_e(support_url)}" style="color:#ff4f9a;text-decoration:none;">{_e(support_url)}</a>.</p>'
        )

    heading = "Tu descarga está lista"
    paras = [
        "El recurso que compraste ya está disponible para descargar. "
        "Entrá a tu cuenta y andá a la sección Mis compras para acceder al archivo.",
    ]
    return _body_html(context, heading, paras, extra_block=extra, cta_html=cta, after_cta_block=after)


def _download_help_html(context):
    library_url = context.get("library_url", "")
    support_email = context.get("support_email", "")

    steps = [
        "Iniciá sesión en tu cuenta de Paola Psicopé.",
        "Andá a la sección Mi cuenta / Mis compras.",
        "Asegurate de estar usando el mismo email con el que hiciste la compra.",
        "Si el recurso no aparece, contactanos y te ayudamos.",
    ]
    extra = _card_block(
        '<p style="margin:0 0 10px;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;">Pasos para encontrar tu descarga:</p>'
        + _bullet_list(steps)
    )

    cta = _cta_button(library_url or _frontend_url() + "/perfil#biblioteca", "Ir a mis compras")

    after = ""
    if support_email:
        after = (
            f'<p style="margin:0;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:14px;">'
            f'Todavía no lo encontrás? Escribinos a '
            f'<a href="mailto:{_e(support_email)}" style="color:#ff4f9a;text-decoration:none;">{_e(support_email)}</a> '
            f'y te vamos a ayudar.</p>'
        )

    heading = "Te ayudamos a encontrar tu descarga"
    paras = [
        "Vimos que tuviste alguna dificultad para acceder a tu recurso. "
        "No te preocupes, te guiamos paso a paso:",
    ]
    return _body_html(context, heading, paras, extra_block=extra, cta_html=cta, after_cta_block=after)


def _new_product_html(context):
    product_title = context.get("product_title", "")
    product_description = context.get("product_description", "")
    product_price = context.get("product_price", "")
    product_url = context.get("product_url", "")

    details = []
    if product_title:
        details.append(("Recurso", product_title))
    if product_price:
        details.append(("Precio", product_price))

    rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#333333;font-family:Helvetica,Arial,sans-serif;font-size:15px;">{_e(label)}</td>'
        f'<td style="padding:6px 12px;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;text-align:right;">{_e(value)}</td></tr>'
        for label, value in details
    )

    desc_block = ""
    if product_description:
        desc_block = (
            f'<p style="margin:8px 0 0;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5;">{_e(product_description)}</p>'
        )

    extra = _card_block(
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;">{rows}</table>'
        f'{desc_block}'
    )

    cta = _cta_button(product_url or _frontend_url() + "/tienda", "Ver producto")

    heading = "Nuevo recurso disponible"
    paras = [
        "Se acaba de publicar un nuevo recurso en Paola Psicopé que puede interesarte:",
    ]
    return _body_html(context, heading, paras, extra_block=extra, cta_html=cta)


def _product_updated_html(context):
    product_title = context.get("product_title", "")
    changes = context.get("changes", [])
    product_url = context.get("product_url", "")

    extra = ""
    if product_title:
        extra += _card_block(
            f'<p style="margin:0;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:16px;font-weight:700;">{_e(product_title)}</p>'
        )

    if changes:
        extra += _card_block(
            '<p style="margin:0 0 10px;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;">Mejoras incluidas:</p>'
            + _bullet_list(changes)
        )

    cta = _cta_button(product_url or _frontend_url() + "/tienda", "Ver actualización")

    heading = "Tu recurso fue actualizado"
    paras = [
        "Uno de los recursos en Paola Psicopé recibió una actualización. "
        "Podés acceder a la nueva versión desde tu cuenta.",
    ]
    return _body_html(context, heading, paras, extra_block=extra, cta_html=cta)


def _abandoned_cart_html(context):
    product_title = context.get("product_title", "")
    product_price = context.get("product_price", "")
    cart_url = context.get("cart_url", "")

    details = []
    if product_title:
        details.append(("Recurso", product_title))
    if product_price:
        details.append(("Precio", product_price))

    rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#333333;font-family:Helvetica,Arial,sans-serif;font-size:15px;">{_e(label)}</td>'
        f'<td style="padding:6px 12px;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;text-align:right;">{_e(value)}</td></tr>'
        for label, value in details
    )

    extra = _card_block(
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;">{rows}</table>'
    )

    cta = _cta_button(cart_url or _frontend_url(), "Volver al carrito")

    heading = "Tu recurso te está esperando"
    paras = [
        "Vimos que estuviste viendo un recurso pero la compra no se completó. "
        "No hay problema, lo guardamos para cuando quieras.",
        "Si tenés alguna duda o querés ayuda para elegir, respondé este email y te contamos más.",
    ]
    return _body_html(context, heading, paras, extra_block=extra, cta_html=cta)


def _support_received_html(context):
    ticket_subject = context.get("ticket_subject", "")
    support_email = context.get("support_email", "")

    extra = ""
    if ticket_subject:
        extra = _card_block(
            f'<p style="margin:0;color:#0f172a;font-family:Helvetica,Arial,sans-serif;font-size:16px;font-weight:700;">{_e(ticket_subject)}</p>'
        )

    cta = _cta_button(_frontend_url(), "Ver sitio")

    after = ""
    if support_email:
        after = (
            f'<p style="margin:0;color:#64748b;font-family:Helvetica,Arial,sans-serif;font-size:14px;">'
            f'Mientras tanto, podés escribirnos a '
            f'<a href="mailto:{_e(support_email)}" style="color:#ff4f9a;text-decoration:none;">{_e(support_email)}</a> '
            f'si necesitás agregar más información.</p>'
        )

    heading = "Recibimos tu consulta"
    paras = [
        "Gracias por escribirnos. Recibimos tu mensaje y lo vamos a revisar pronto. "
        "Te vamos a responder a la brevedad.",
    ]
    return _body_html(context, heading, paras, extra_block=extra, cta_html=cta, after_cta_block=after)


# ------- Plain text builders -------

def _verify_account_text(context):
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Ingresá el siguiente código para terminar de crear tu cuenta en Paola Psicopé:",
        "",
        f"Código: {context.get('code', '')}",
        "",
        f"Este código vence en {context.get('expires_minutes', '10')} minutos.",
        "Si no pediste crear esta cuenta, podés ignorar este email.",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


def _welcome_text(context):
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Gracias por sumarte al espacio de Paola Psicopé. Estamos felices de tenerte en la comunidad.",
        "",
        "Acá vas a encontrar recursos psicopedagógicos diseñados para familias, docentes y profesionales.",
        "",
        "Desde tu cuenta podés acceder a todos tus recursos comprados y seguir tus descargas.",
        "",
        f"Explorar tienda: {context.get('store_url', '')}",
        f"Mi cuenta: {context.get('account_url', '')}",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


def _password_reset_text(context):
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Recibimos una solicitud para cambiar la contraseña de tu cuenta en Paola Psicopé.",
        "",
        f"Código: {context.get('code', '')}",
        "",
        "Si no pediste restablecer tu contraseña, podés ignorar este email.",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


def _purchase_confirmed_text(context):
    guest_checkout = bool(context.get("guest_checkout"))
    download_links = context.get("download_links", []) or []
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Recibimos tu compra y ya está confirmada.",
        (
            "Descargá los materiales desde los enlaces personales de este email."
            if guest_checkout
            else "El recurso queda disponible en tu cuenta para que lo descargues cuando lo necesites."
        ),
        "",
        f"Producto: {context.get('product_title', '')}",
        f"Orden: {context.get('order_id', '')}",
        f"Total: {context.get('total', '')}",
        f"Estado: {context.get('payment_status', '')}",
        "",
        *(f"Descargar {item.get('label') or 'material'}: {item.get('url', '')}" for item in download_links),
        *([] if download_links else [f"Ver detalle: {context.get('order_url', '')}"]),
        "",
        "Guardá este email: los enlaces de invitado están disponibles durante 30 días."
        if guest_checkout
        else "Por seguridad no adjuntamos archivos en este email.",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


def _download_ready_text(context):
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "El recurso que compraste ya está disponible para descargar.",
        "",
        f"Recurso: {context.get('product_title', '')}",
        f"Tipo: {context.get('file_type', '')}",
        "",
        f"Ir a mis compras: {context.get('library_url', '')}",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


def _download_help_text(context):
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Vimos que tuviste alguna dificultad para acceder a tu recurso.",
        "Te guiamos paso a paso:",
        "",
        "1. Iniciá sesión en tu cuenta de Paola Psicopé.",
        "2. Andá a la sección Mi cuenta / Mis compras.",
        "3. Asegurate de usar el mismo email con el que hiciste la compra.",
        "4. Si el recurso no aparece, contactanos y te ayudamos.",
        "",
        f"Ir a mis compras: {context.get('library_url', '')}",
        "",
        f"Todavía no lo encontrás? Escribinos a {context.get('support_email', '')}",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


def _new_product_text(context):
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Se acaba de publicar un nuevo recurso en Paola Psicopé que puede interesarte:",
        "",
        f"Recurso: {context.get('product_title', '')}",
        f"Precio: {context.get('product_price', '')}",
        f"Descripción: {context.get('product_description', '')}",
        "",
        f"Ver producto: {context.get('product_url', '')}",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


def _product_updated_text(context):
    changes = context.get("changes", [])
    changes_text = ""
    if changes:
        changes_text = "\nMejoras incluidas:\n" + "\n".join(f"- {c}" for c in changes)

    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Uno de los recursos en Paola Psicopé recibió una actualización.",
        f"Podés acceder a la nueva versión desde tu cuenta.",
        "",
        f"Recurso: {context.get('product_title', '')}",
        changes_text,
        "",
        f"Ver actualización: {context.get('product_url', '')}",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(filter(None, lines))


def _abandoned_cart_text(context):
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Vimos que estuviste viendo un recurso pero la compra no se completó.",
        "No hay problema, lo guardamos para cuando quieras.",
        "",
        f"Recurso: {context.get('product_title', '')}",
        f"Precio: {context.get('product_price', '')}",
        "",
        f"Volver al carrito: {context.get('cart_url', '')}",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


def _support_received_text(context):
    lines = [
        f"Hola {context.get('name', '')},",
        "",
        "Gracias por escribirnos. Recibimos tu mensaje y lo vamos a revisar pronto.",
        "",
        f"Asunto: {context.get('ticket_subject', 'Sin asunto')}",
        "",
        f"Sitio web: {_frontend_url()}",
        "",
        "Paola Psicopé",
    ]
    return "\n".join(lines)


# ------- Subject line builders -------

def _default_subject(template_key, context):
    subjects = {
        "verify_account": f"Tu código de verificación es {context.get('code', '')}",
        "welcome": "Bienvenida a Paola Psicopé",
        "password_reset": "Restablecé tu contraseña",
        "purchase_confirmed": "Compra confirmada",
        "download_ready": "Tu descarga está lista",
        "download_help": "Te ayudamos a encontrar tu descarga",
        "new_product": "Nuevo recurso disponible",
        "product_updated": "Tu recurso fue actualizado",
        "abandoned_cart": "Tu recurso te está esperando",
        "support_received": "Recibimos tu consulta",
    }
    return subjects.get(template_key, "Paola Psicopé")


# ------- Registry maps -------

_HTML_BUILDERS = {
    "verify_account": _verify_account_html,
    "welcome": _welcome_html,
    "password_reset": _password_reset_html,
    "purchase_confirmed": _purchase_confirmed_html,
    "download_ready": _download_ready_html,
    "download_help": _download_help_html,
    "new_product": _new_product_html,
    "product_updated": _product_updated_html,
    "abandoned_cart": _abandoned_cart_html,
    "support_received": _support_received_html,
}

_TEXT_BUILDERS = {
    "verify_account": _verify_account_text,
    "welcome": _welcome_text,
    "password_reset": _password_reset_text,
    "purchase_confirmed": _purchase_confirmed_text,
    "download_ready": _download_ready_text,
    "download_help": _download_help_text,
    "new_product": _new_product_text,
    "product_updated": _product_updated_text,
    "abandoned_cart": _abandoned_cart_text,
    "support_received": _support_received_text,
}


def render_email_template(template_key, context):
    if template_key not in _HTML_BUILDERS:
        raise ValueError(f"Unknown email template: '{template_key}'")

    hero = _hero_url(template_key)
    preheader = context.get("preheader", "")
    subject = context.get("subject") or _default_subject(template_key, context)

    body_html = _HTML_BUILDERS[template_key](context)
    full_html = _base_html(body_html, hero, preheader)
    text = _TEXT_BUILDERS[template_key](context)

    return {
        "subject": subject,
        "html": full_html,
        "text": text,
    }
