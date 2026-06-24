import { requireAdmin } from "@/server/middleware/auth";
import { deleteProduct, getProductById, updateProduct } from "@/server/services/products";
import { validateProductUpdate } from "@/server/validators/products";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const product = await getProductById(id);
    if (!product) {
      return Response.json({ error: "Producto no encontrado." }, { status: 404 });
    }
    return Response.json({ product });
  } catch (error) {
    console.error("GET /api/products/[id] error:", error);
    return Response.json({ error: "Error al obtener producto." }, { status: 500 });
  }
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    await requireAdmin(request);
    const { id } = await params;
    const body = await request.json();
    const data = validateProductUpdate(body);
    const product = await updateProduct(id, data);
    return Response.json({ product });
  } catch (error) {
    console.error("PUT /api/products/[id] error:", error);
    const message = error instanceof Error ? error.message : "Error al actualizar producto.";
    const status = message === "No autenticado" || message === "Sesión inválida" || message === "No autorizado" ? 401 : 500;
    return Response.json({ error: message }, { status });
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    await requireAdmin(request);
    const { id } = await params;
    await deleteProduct(id);
    return Response.json({ ok: true });
  } catch (error) {
    console.error("DELETE /api/products/[id] error:", error);
    const message = error instanceof Error ? error.message : "Error al eliminar producto.";
    const status = message === "No autenticado" || message === "Sesión inválida" || message === "No autorizado" ? 401 : 500;
    return Response.json({ error: message }, { status });
  }
}
