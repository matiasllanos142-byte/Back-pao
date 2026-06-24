import { CATEGORY_LABELS } from "@/lib/constants";

const LEVELS = ["Inicial", "Intermedio", "Avanzado"];
const AGE_OPTIONS = ["4-6 años", "6-8 años", "8-10 años", "10-12 años", "Adolescentes", "Adultos"];

function isString(value: unknown): value is string {
  return typeof value === "string";
}

export function validateProductBody(body: Record<string, unknown>) {
  const title = isString(body.title) ? body.title.trim() : "";
  const description = isString(body.description) ? body.description.trim() : "";
  const category = isString(body.category) ? body.category.trim() : "";
  const level = isString(body.level) ? body.level.trim() : "";
  const age = isString(body.age) ? body.age.trim() : "";

  if (!title) throw new Error("El título es obligatorio.");
  if (!description) throw new Error("La descripción es obligatoria.");
  if (!category || !(category in CATEGORY_LABELS)) {
    throw new Error("La categoría no es válida.");
  }
  if (!LEVELS.includes(level)) throw new Error("El nivel no es válido.");
  if (!AGE_OPTIONS.includes(age)) throw new Error("El rango de edad no es válido.");

  const price = Number(body.price);
  if (!Number.isFinite(price) || price < 0) {
    throw new Error("El precio no es válido.");
  }

  const features = Array.isArray(body.features)
    ? body.features.filter((f): f is string => typeof f === "string" && f.trim() !== "")
    : [];

  const objectives = Array.isArray(body.objectives)
    ? body.objectives.filter((o): o is string => typeof o === "string" && o.trim() !== "")
    : [];

  return {
    title,
    description,
    price,
    categorySlug: category,
    level,
    age,
    badge: isString(body.badge) && body.badge.trim() ? body.badge.trim() : null,
    featured: body.featured === true,
    image: isString(body.image) && body.image.trim() ? body.image.trim() : "/images/products/placeholder.jpg",
    features,
    objectives,
  };
}

export function validateProductUpdate(body: Record<string, unknown>) {
  const data: Record<string, unknown> = {};

  if (body.title !== undefined) {
    const title = isString(body.title) ? body.title.trim() : "";
    if (!title) throw new Error("El título no puede estar vacío.");
    data.title = title;
  }

  if (body.description !== undefined) {
    const description = isString(body.description) ? body.description.trim() : "";
    if (!description) throw new Error("La descripción no puede estar vacía.");
    data.description = description;
  }

  if (body.price !== undefined) {
    const price = Number(body.price);
    if (!Number.isFinite(price) || price < 0) {
      throw new Error("El precio no es válido.");
    }
    data.price = price;
  }

  if (body.category !== undefined) {
    const category = isString(body.category) ? body.category.trim() : "";
    if (!(category in CATEGORY_LABELS)) throw new Error("La categoría no es válida.");
    data.categorySlug = category;
  }

  if (body.level !== undefined) {
    const level = isString(body.level) ? body.level.trim() : "";
    if (!LEVELS.includes(level)) throw new Error("El nivel no es válido.");
    data.level = level;
  }

  if (body.age !== undefined) {
    const age = isString(body.age) ? body.age.trim() : "";
    if (!AGE_OPTIONS.includes(age)) throw new Error("El rango de edad no es válido.");
    data.age = age;
  }

  if (body.badge !== undefined) {
    data.badge = isString(body.badge) && body.badge.trim() ? body.badge.trim() : null;
  }

  if (body.featured !== undefined) {
    data.featured = body.featured === true;
  }

  if (body.image !== undefined) {
    data.image = isString(body.image) && body.image.trim() ? body.image.trim() : "/images/products/placeholder.jpg";
  }

  if (body.features !== undefined) {
    data.features = Array.isArray(body.features)
      ? JSON.stringify(
          body.features.filter((f): f is string => typeof f === "string" && f.trim() !== "")
        )
      : "[]";
  }

  if (body.objectives !== undefined) {
    data.objectives = Array.isArray(body.objectives)
      ? JSON.stringify(
          body.objectives.filter((o): o is string => typeof o === "string" && o.trim() !== "")
        )
      : "[]";
  }

  return data;
}
