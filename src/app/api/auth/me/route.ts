import { getCurrentUser } from "@/server/middleware/auth";

export async function GET(request: Request) {
  try {
    const user = await getCurrentUser(request);
    if (!user) {
      return Response.json({ user: null });
    }
    return Response.json({
      user: { ...user, createdAt: user.createdAt.toISOString() },
    });
  } catch (error) {
    console.error("Me error:", error);
    return Response.json({ user: null });
  }
}
