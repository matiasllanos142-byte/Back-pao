import { requireAdmin } from "@/server/middleware/auth";
import { createProduct, getProducts } from "@/server/services/products";
import { validateProductBody } from "@/server/validators/products";

export async function GET() {
  try {
    const products = await getProducts();
    return Response.json({ products });
  } catch (error) {
    console.error("GET /api/products error:", error);
    return Response.json({ error: "Error al obtener productos." }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    await requireAdmin(request);
    const body = await request.json();
    const data = validateProductBody(body);
    const product = await createProduct(data);
    return Response.json({ product }, { status: 201 });
  } catch (error) {
    console.error("POST /api/products error:", error);
    const message = error instanceof Error ? error.message : "Error al crear producto.";
    const status = message === "No autenticado" || message === "Sesión inválida" || message === "No autorizado" ? 401 : 500;
    return Response.json({ error: message }, { status });
  }
}
