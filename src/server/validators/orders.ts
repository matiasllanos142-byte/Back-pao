const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateCustomer(customer: unknown): { name: string; email: string } {
  if (!customer || typeof customer !== "object") {
    throw new Error("Los datos del cliente son obligatorios.");
  }
  const { name, email } = customer as Record<string, unknown>;

  if (typeof name !== "string" || !name.trim()) {
    throw new Error("El nombre del cliente es obligatorio.");
  }

  if (typeof email !== "string" || !email.trim() || !EMAIL_REGEX.test(email.trim())) {
    throw new Error("El email del cliente no es válido.");
  }

  return { name: name.trim(), email: email.trim().toLowerCase() };
}

export function validateOrderItems(items: unknown): Array<{ productId: string; quantity: number }> {
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error("La orden debe tener al menos un producto.");
  }

  return items.map((item, index) => {
    if (!item || typeof item !== "object") {
      throw new Error(`Item ${index + 1} inválido.`);
    }
    const { productId, quantity } = item as Record<string, unknown>;

    if (typeof productId !== "string" || !productId.trim()) {
      throw new Error(`El producto en el item ${index + 1} no es válido.`);
    }

    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty < 1) {
      throw new Error(`La cantidad en el item ${index + 1} no es válida.`);
    }

    return { productId: productId.trim(), quantity: qty };
  });
}

export function validatePaymentItems(
  items: unknown
): Array<{ productId: string; title: string; price: number; quantity: number }> {
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error("La orden debe tener al menos un producto.");
  }

  return items.map((item, index) => {
    if (!item || typeof item !== "object") {
      throw new Error(`Item ${index + 1} inválido.`);
    }
    const { productId, title, price, quantity } = item as Record<string, unknown>;

    if (typeof productId !== "string" || !productId.trim()) {
      throw new Error(`El producto en el item ${index + 1} no es válido.`);
    }
    if (typeof title !== "string" || !title.trim()) {
      throw new Error(`El título en el item ${index + 1} no es válido.`);
    }
    const unitPrice = Number(price);
    if (!Number.isFinite(unitPrice) || unitPrice < 0) {
      throw new Error(`El precio en el item ${index + 1} no es válido.`);
    }
    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty < 1) {
      throw new Error(`La cantidad en el item ${index + 1} no es válida.`);
    }

    return { productId: productId.trim(), title: title.trim(), price: unitPrice, quantity: qty };
  });
}
