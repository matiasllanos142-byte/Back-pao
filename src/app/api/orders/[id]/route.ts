import { getCurrentUser } from "@/server/middleware/auth";
import { getOrderById } from "@/server/services/orders";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const order = await getOrderById(id);

    if (!order) {
      return Response.json({ error: "Orden no encontrada." }, { status: 404 });
    }

    const user = await getCurrentUser(request);
    if (!user) {
      return Response.json({ error: "No autenticado." }, { status: 401 });
    }

    if (!user.isAdmin && order.customer.email !== user.email) {
      return Response.json({ error: "No autorizado." }, { status: 403 });
    }

    return Response.json({ order });
  } catch (error) {
    console.error("GET /api/orders/[id] error:", error);
    return Response.json({ error: "Error al obtener orden." }, { status: 500 });
  }
}
