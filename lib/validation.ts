// Helpers de validación de inputs
// Centralizamos para reusar y tener validación consistente.

export function validateFixtureId(id: string | undefined): number | null {
  if (!id) return null;
  // Solo dígitos, max 10 chars (limita a IDs de BD razonables)
  if (!/^\d{1,10}$/.test(id)) return null;
  const n = parseInt(id, 10);
  if (isNaN(n) || n <= 0) return null;
  return n;
}

export function validateTeamId(id: string | undefined): number | null {
  return validateFixtureId(id); // misma validación (mismo tipo de IDs)
}

export function sanitizeString(str: string | null | undefined, maxLen = 500): string {
  if (!str) return "";
  // Truncar a longitud máxima
  return String(str).slice(0, maxLen);
}