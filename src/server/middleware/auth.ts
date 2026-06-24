import { prisma } from "@/server/lib/prisma";
import { getSessionToken, verifyToken, type TokenPayload } from "@/server/lib/auth";

export async function requireAuth(request: Request): Promise<TokenPayload> {
  const token = getSessionToken(request);
  if (!token) {
    throw new Error("No autenticado");
  }
  const payload = await verifyToken(token);
  if (!payload) {
    throw new Error("Sesión inválida");
  }
  return payload;
}

export async function requireAdmin(request: Request): Promise<TokenPayload> {
  const payload = await requireAuth(request);
  if (!payload.isAdmin) {
    throw new Error("No autorizado");
  }
  return payload;
}

export async function getCurrentUser(request: Request) {
  const token = getSessionToken(request);
  if (!token) return null;
  const payload = await verifyToken(token);
  if (!payload) return null;

  const user = await prisma.user.findUnique({
    where: { id: payload.userId },
    select: { id: true, name: true, email: true, isAdmin: true, createdAt: true },
  });

  if (!user) return null;
  return user;
}
