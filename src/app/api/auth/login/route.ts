import { prisma } from "@/server/lib/prisma";
import { createToken, setSessionCookie } from "@/server/lib/auth";
import { validateEmail } from "@/server/validators/auth";
import bcrypt from "bcrypt";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const email = validateEmail(body.email);

    if (typeof body.password !== "string" || !body.password) {
      return Response.json({ error: "La contraseña es obligatoria." }, { status: 400 });
    }

    const user = await prisma.user.findUnique({ where: { email } });
    if (!user) {
      return Response.json({ error: "Email o contraseña incorrectos." }, { status: 401 });
    }

    const valid = await bcrypt.compare(body.password, user.password);
    if (!valid) {
      return Response.json({ error: "Email o contraseña incorrectos." }, { status: 401 });
    }

    const token = await createToken({
      userId: user.id,
      email: user.email,
      isAdmin: user.isAdmin,
    });

    const response = Response.json({
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        isAdmin: user.isAdmin,
        createdAt: user.createdAt.toISOString(),
      },
    });

    return setSessionCookie(response, token);
  } catch (error) {
    console.error("Login error:", error);
    const message = error instanceof Error ? error.message : "Error interno del servidor.";
    return Response.json({ error: message }, { status: 500 });
  }
}
