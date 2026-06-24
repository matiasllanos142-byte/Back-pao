import { MercadoPagoConfig, Preference } from "mercadopago";
import { getCurrentUser } from "@/server/middleware/auth";
import { createOrder } from "@/server/services/orders";
import { validateCustomer, validatePaymentItems } from "@/server/validators/orders";

const MP_ACCESS_TOKEN = process.env.MP_ACCESS_TOKEN;

export async function POST(request: Request) {
  try {
    const user = await getCurrentUser(request);
    const body = await request.json();

    const customer = validateCustomer(body.customer);
    const items = validatePaymentItems(body.items);

    const order = await createOrder({
      userId: user?.id ?? null,
      customerName: customer.name,
      customerEmail: customer.email,
      items: items.map((i) => ({ productId: i.productId, quantity: i.quantity })),
    });

    const baseUrl = new URL(request.url).origin;

    if (!MP_ACCESS_TOKEN) {
      return Response.json({
        demo: true,
        orderId: order.id,
        init_point: `${baseUrl}/checkout/success?order_id=${order.id}`,
      });
    }

    const client = new MercadoPagoConfig({ accessToken: MP_ACCESS_TOKEN });
    const preference = new Preference(client);

    const result = await preference.create({
      body: {
        items: items.map((i) => ({
          id: i.productId,
          title: i.title,
          unit_price: i.price,
          quantity: i.quantity,
          currency_id: "ARS",
        })),
        payer: { name: customer.name, email: customer.email },
        back_urls: {
          success: `${baseUrl}/checkout/success`,
          failure: `${baseUrl}/checkout/failure`,
          pending: `${baseUrl}/checkout/failure`,
        },
        auto_return: "approved",
        external_reference: order.id,
      },
    });

    return Response.json({ init_point: result.init_point, orderId: order.id });
  } catch (error) {
    console.error("Error creating payment:", error);
    const message = error instanceof Error ? error.message : "Error al procesar el pago.";
    return Response.json({ error: message }, { status: 500 });
  }
}
