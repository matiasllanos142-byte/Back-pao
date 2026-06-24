import type { CategorySlug } from "@/types";

export const CATEGORY_LABELS: Record<CategorySlug, string> = {
  estimulacion: "Estimulación Cognitiva",
  lectoescritura: "Lectoescritura",
  dislexia: "Dislexia",
  matematica: "Matemática",
  "atencion-memoria": "Atención y Memoria",
  "funciones-ejecutivas": "Funciones Ejecutivas",
};

export const SITE_CONFIG = {
  name: "Paola Psicopé",
  tagline: "Recursos psicopedagógicos para aprender y acompañar",
  description:
    "Recursos psicopedagógicos digitales creados por Paola, psicopedagoga. Materiales diseñados con fundamento para acompañar procesos de aprendizaje.",
  url: "https://paolapsicope.com",
} as const;

export const NAV_LINKS = [
  { label: "Inicio", href: "/" },
  { label: "Tienda", href: "/tienda" },
  { label: "Categorías", href: "/categorias" },
  { label: "Sobre mí", href: "/sobre-nosotros" },
  { label: "Contacto", href: "/contacto" },
] as const;

export const HOW_IT_STEPS = [
  {
    number: "01",
    title: "Elegí el recurso",
    description:
      "Explorá por categoría o usá los filtros para encontrar el material que mejor se adapte a lo que necesitás.",
  },
  {
    number: "02",
    title: "Compralo al instante",
    description:
      "Completá tu compra de forma rápida y segura. Sin esperas ni trámites.",
  },
  {
    number: "03",
    title: "Descargalo y usalo",
    description:
      "Recibí tu PDF listo para imprimir o usar en pantalla. Directo a tu correo.",
  },
] as const;

export const DIFFERENTIALS = [
  {
    title: "Diseñado con fundamento",
    description:
      "Cada recurso lo elaboro con base en evidencia científica y mi experiencia en el ámbito psicopedagógico.",
    icon: "GraduationCap",
  },
  {
    title: "Acompañamiento cercano",
    description:
      "¿Dudas sobre cómo aplicar un recurso? Escribime y te oriento personalmente.",
    icon: "Headphones",
  },
  {
    title: "Actualizaciones gratuitas",
    description:
      "Los materiales se mejoran periódicamente. Comprás una vez, recibís siempre las versiones actualizadas.",
    icon: "RefreshCw",
  },
  {
    title: "Descarga inmediata",
    description:
      "Acceso instantáneo a tus materiales después de la compra. Sin demoras, sin envíos.",
    icon: "Download",
  },
] as const;
