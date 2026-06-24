import { prisma } from "@/server/lib/prisma";
import { OrderStatus } from "@/generated/prisma/client";
import { serializeProduct } from "@/server/services/products";

export interface OrderItemInput {
  productId: string;
  quantity: number;
}

export function serializeOrder(order: {
  id: string;
  userId: string | null;
  total: number;
  status: string;
  customerName: string;
  customerEmail: string;
  createdAt: Date;
  items: Array<{
    quantity: number;
    price: number;
    product: {
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
    };
  }>;
}) {
  return {
    id: order.id,
    total: order.total,
    status: order.status,
    createdAt: order.createdAt.toISOString(),
    customer: { name: order.customerName, email: order.customerEmail },
    items: order.items.map((i) => ({
      quantity: i.quantity,
      price: i.price,
      product: serializeProduct(i.product),
    })),
  };
}

export async function getOrdersByUser(userId: string) {
  const orders = await prisma.order.findMany({
    where: { userId },
    include: {
      items: {
        include: { product: true },
      },
    },
    orderBy: { createdAt: "desc" },
  });
  return orders.map((o) => serializeOrder(o));
}

export async function getOrderById(id: string) {
  const order = await prisma.order.findUnique({
    where: { id },
    include: {
      items: {
        include: { product: true },
      },
    },
  });
  if (!order) return null;
  return serializeOrder(order);
}

export async function createOrder(data: {
  userId: string | null;
  customerName: string;
  customerEmail: string;
  items: OrderItemInput[];
  status?: OrderStatus;
}) {
  const products = await prisma.product.findMany({
    where: {
      id: { in: data.items.map((i) => i.productId) },
      isActive: true,
    },
  });

  const productMap = new Map(products.map((p) => [p.id, p]));
  let total = 0;
  const orderItems: Array<{ productId: string; quantity: number; price: number }> = [];

  for (const item of data.items) {
    const product = productMap.get(item.productId);
    if (!product) {
      throw new Error(`Producto no encontrado: ${item.productId}`);
    }
    if (!Number.isInteger(item.quantity) || item.quantity < 1) {
      throw new Error(`Cantidad inválida para ${product.title}`);
    }
    total += product.price * item.quantity;
    orderItems.push({
      productId: product.id,
      quantity: item.quantity,
      price: product.price,
    });
  }

  const order = await prisma.order.create({
    data: {
      userId: data.userId,
      total,
      status: data.status ?? OrderStatus.pendiente,
      customerName: data.customerName,
      customerEmail: data.customerEmail,
      items: {
        create: orderItems,
      },
    },
    include: {
      items: {
        include: { product: true },
      },
    },
  });

  return serializeOrder(order);
}

export async function updateOrderStatus(id: string, status: OrderStatus) {
  const order = await prisma.order.update({
    where: { id },
    data: { status },
    include: {
      items: {
        include: { product: true },
      },
    },
  });
  return serializeOrder(order);
}
