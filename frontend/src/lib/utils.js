import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

// Microcopy unificado de la política de contraseñas (12+ · mayús · minús · número · símbolo).
export const PASSWORD_POLICY_HINT =
  "La contraseña debe tener un mínimo de 12 caracteres e incluir al menos una letra mayúscula, una letra minúscula, un número y un símbolo especial.";

// Validación cliente espejo de `validate_password_policy` del backend.
export function passwordMeetsPolicy(pw) {
  const p = pw || "";
  return p.length >= 12 && /[A-Z]/.test(p) && /[a-z]/.test(p) && /\d/.test(p) && /[^A-Za-z0-9]/.test(p);
}
