import { prisma } from "@/server/lib/prisma";
import { createToken, setSessionCookie } from "@/server/lib/auth";
import { validateEmail, validatePassword, validateName } from "@/server/validators/auth";
import bcrypt from "bcrypt";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const name = validateName(body.name);
    const email = validateEmail(body.email);
    const password = validatePassword(body.password);

    const existing = await prisma.user.findUnique({ where: { email } });
    if (existing) {
      return Response.json({ error: "Este email ya está registrado." }, { status: 400 });
    }

    const hashedPassword = await bcrypt.hash(password, 12);
    const adminEmail = process.env.ADMIN_EMAIL?.toLowerCase();
    const isAdmin = adminEmail ? email === adminEmail : false;

    const user = await prisma.user.create({
      data: {
        name,
        email,
        password: hashedPassword,
        isAdmin,
      },
    });

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
    console.error("Register error:", error);
    const message = error instanceof Error ? error.message : "Error interno del servidor.";
    return Response.json({ error: message }, { status: 500 });
  }
}
