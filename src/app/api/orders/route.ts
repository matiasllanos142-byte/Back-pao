import { getCurrentUser } from "@/server/middleware/auth";
import { createOrder, getOrdersByUser } from "@/server/services/orders";
import { validateCustomer, validateOrderItems } from "@/server/validators/orders";

export async function GET(request: Request) {
  try {
    const user = await getCurrentUser(request);
    if (!user) {
      return Response.json({ orders: [] });
    }
    const orders = await getOrdersByUser(user.id);
    return Response.json({ orders });
  } catch (error) {
    console.error("GET /api/orders error:", error);
    return Response.json({ orders: [] });
  }
}

export async function POST(request: Request) {
  try {
    const user = await getCurrentUser(request);
    const body = await request.json();

    const customer = validateCustomer(body.customer);
    const items = validateOrderItems(body.items);

    const order = await createOrder({
      userId: user?.id ?? null,
      customerName: customer.name,
      customerEmail: customer.email,
      items,
    });

    return Response.json({ order }, { status: 201 });
  } catch (error) {
    console.error("POST /api/orders error:", error);
    const message = error instanceof Error ? error.message : "Error al crear orden.";
    return Response.json({ error: message }, { status: 400 });
  }
}
