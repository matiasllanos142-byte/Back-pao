import { SignJWT, jwtVerify } from "jose";

function getJwtSecret(): Uint8Array {
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    throw new Error("JWT_SECRET no está definida en las variables de entorno.");
  }
  return new TextEncoder().encode(secret);
}

export interface TokenPayload {
  userId: string;
  email: string;
  isAdmin: boolean;
}

export async function createToken(payload: TokenPayload): Promise<string> {
  const secret = getJwtSecret();
  return new SignJWT({
    userId: payload.userId,
    email: payload.email,
    isAdmin: payload.isAdmin,
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("7d")
    .sign(secret);
}

export async function verifyToken(token: string): Promise<TokenPayload | null> {
  try {
    const secret = getJwtSecret();
    const { payload } = await jwtVerify(token, secret);
    return {
      userId: String(payload.userId),
      email: String(payload.email),
      isAdmin: Boolean(payload.isAdmin),
    };
  } catch {
    return null;
  }
}

const COOKIE_NAME = "session";
const ONE_WEEK_SECONDS = 60 * 60 * 24 * 7;

export function setSessionCookie(response: Response, token: string): Response {
  const isSecure = process.env.NODE_ENV === "production";
  const cookie = `${COOKIE_NAME}=${token}; HttpOnly; Path=/; Max-Age=${ONE_WEEK_SECONDS}; SameSite=Lax${isSecure ? "; Secure" : ""}`;
  response.headers.set("Set-Cookie", cookie);
  return response;
}

export function clearSessionCookie(response: Response): Response {
  const isSecure = process.env.NODE_ENV === "production";
  const cookie = `${COOKIE_NAME}=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax${isSecure ? "; Secure" : ""}`;
  response.headers.set("Set-Cookie", cookie);
  return response;
}

export function getSessionToken(request: Request): string | null {
  const cookieHeader = request.headers.get("cookie") || "";
  const sessionCookie = cookieHeader
    .split(";")
    .find((c) => c.trim().startsWith(`${COOKIE_NAME}=`));
  if (!sessionCookie) return null;
  return sessionCookie.split("=")[1]?.trim() || null;
}
