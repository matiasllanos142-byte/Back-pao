import { prisma } from "@/server/lib/prisma";

export function serializeProduct(product: {
  id: string;
  title: string;
  description: string;
  price: number;
  categorySlug: string;
  image: string;
  badge: string | null;
  featured: boolean;
  age: string;
  level: string;
  features: string;
  objectives: string;
  createdAt: Date;
}) {
  try {
    return {
      ...product,
      category: product.categorySlug,
      features: JSON.parse(product.features || "[]"),
      objectives: JSON.parse(product.objectives || "[]"),
    };
  } catch {
    return {
      ...product,
      category: product.categorySlug,
      features: [],
      objectives: [],
    };
  }
}

export async function getProducts() {
  const products = await prisma.product.findMany({
    where: { isActive: true },
    include: { category: true },
    orderBy: { createdAt: "desc" },
  });
  return products.map((p) => serializeProduct(p));
}

export async function getProductById(id: string) {
  const product = await prisma.product.findUnique({
    where: { id, isActive: true },
    include: { category: true },
  });
  if (!product) return null;
  return serializeProduct(product);
}

export async function createProduct(data: {
  title: string;
  description: string;
  price: number;
  categorySlug: string;
  image: string;
  badge: string | null;
  featured: boolean;
  age: string;
  level: string;
  features: string[];
  objectives: string[];
}) {
  const product = await prisma.product.create({
    data: {
      ...data,
      features: JSON.stringify(data.features),
      objectives: JSON.stringify(data.objectives),
    },
    include: { category: true },
  });
  return serializeProduct(product);
}

export async function updateProduct(
  id: string,
  data: Record<string, unknown>
) {
  const product = await prisma.product.update({
    where: { id },
    data,
    include: { category: true },
  });
  return serializeProduct(product);
}

export async function deleteProduct(id: string) {
  await prisma.product.update({
    where: { id },
    data: { isActive: false },
  });
}
