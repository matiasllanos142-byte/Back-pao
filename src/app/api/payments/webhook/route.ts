import { prisma } from "@/server/lib/prisma";
import { OrderStatus } from "@/generated/prisma/client";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    if (body.type === "payment" && body.data?.id) {
      const orderId = body.data.external_reference;
      const status = body.data.status;

      if (orderId && status === "approved") {
        await prisma.order.update({
          where: { id: orderId },
          data: { status: OrderStatus.completada, paymentId: String(body.data.id) },
        });
      }
    }

    return Response.json({ ok: true });
  } catch (error) {
    console.error("Webhook error:", error);
    return Response.json({ ok: true });
  }
}
