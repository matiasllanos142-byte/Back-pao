import { clearSessionCookie } from "@/server/lib/auth";

export async function POST() {
  const response = Response.json({ ok: true });
  return clearSessionCookie(response);
}
