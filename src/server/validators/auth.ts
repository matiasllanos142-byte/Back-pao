const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateEmail(email: unknown): string {
  if (typeof email !== "string" || !email.trim()) {
    throw new Error("El email es obligatorio.");
  }
  const normalized = email.trim().toLowerCase();
  if (!EMAIL_REGEX.test(normalized)) {
    throw new Error("El email no es válido.");
  }
  return normalized;
}

export function validatePassword(password: unknown): string {
  if (typeof password !== "string" || !password) {
    throw new Error("La contraseña es obligatoria.");
  }
  if (password.length < 6) {
    throw new Error("La contraseña debe tener al menos 6 caracteres.");
  }
  return password;
}

export function validateName(name: unknown): string {
  if (typeof name !== "string" || !name.trim()) {
    throw new Error("El nombre es obligatorio.");
  }
  const trimmed = name.trim();
  if (trimmed.length < 2) {
    throw new Error("El nombre debe tener al menos 2 caracteres.");
  }
  return trimmed;
}
