export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;

  if (typeof window !== "undefined") {
    return `${window.location.origin}${normalized}`;
  }

  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (baseUrl) {
    return `${baseUrl}${normalized}`;
  }

  return normalized;
}

export async function apiFetch(
  path: string,
  init?: RequestInit
): Promise<Response> {
  return fetch(apiUrl(path), {
    ...init,
    credentials: "include",
  });
}
