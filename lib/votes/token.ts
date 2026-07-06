// Token utility para links de votación
//
// Esquema:
//   token = base32(sha256(SECRET_SALT + ':' + fixtureId))[:8]
//
// Propiedades:
// - Bidireccional con caché: dado un token, lookup O(1) en memoria
// - Corto: 8 caracteres base32 (A-Z2-7 sin ambiguos)
// - No expone el fixture_id directamente en la URL.
// - Requiere SECRET_SALT para evitar enumeración.

import crypto from "crypto";

const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // sin 0/O/1/I/L

function base32(bytes: Buffer): string {
  let bits = 0;
  let value = 0;
  let out = "";
  for (const b of bytes) {
    value = (value << 8) | b;
    bits += 8;
    while (bits >= 5) {
      out += ALPHABET[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) out += ALPHABET[(value << (5 - bits)) & 31];
  return out;
}

function getSalt(): string {
  return process.env.VOTES_TOKEN_SALT || "quinielas-lol-default-salt";
}

/**
 * Genera el token público para un fixture_id.
 * Determinístico: misma entrada → mismo token.
 */
export function makeToken(fixtureId: number): string {
  const input = `${getSalt()}:${fixtureId}`;
  const hash = crypto.createHash("sha256").update(input).digest();
  return base32(hash.subarray(0, 5)).slice(0, 8);
}

/**
 * Valida el formato del token.
 */
export function isValidToken(token: string): boolean {
  return /^[A-HJ-NP-Z2-9]{8}$/.test(token);
}

// ── Caché en memoria: token → fixtureId ──
// Para evitar iterar 1500+ IDs en cada request.
// TTL de 5 minutos; se rehidrata si pasa ese tiempo.

interface CacheEntry {
  byToken: Map<string, number>;
  expiresAt: number;
}

const globalForTokenCache = global as unknown as {
  voteTokenCache?: CacheEntry;
};

const CACHE_TTL_MS = 5 * 60 * 1000;

async function loadTokenIndex(db: any): Promise<Map<string, number>> {
  // Trae todos los IDs de partidos (suficientemente acotado: ~3,234 en Liga MX).
  // Tarda ~5-15ms en SQLite. Cacheado 5 min.
  try {
    const rows = db
      .prepare(
        `SELECT id FROM fixtures WHERE league_id = 743 ORDER BY id DESC`,
      )
      .all() as { id: number }[];
    const map = new Map<string, number>();
    for (const r of rows) {
      map.set(makeToken(r.id), r.id);
    }
    return map;
  } catch (err) {
    console.error("[votes] loadTokenIndex error:", err);
    return new Map();
  }
}

/**
 * Resuelve un token a fixture_id usando un índice cacheado en memoria.
 * @param db Better-sqlite3 instance (la BD principal, read-only)
 */
export async function resolveTokenAsync(
  token: string,
  db: any,
): Promise<number | null> {
  if (!isValidToken(token)) return null;

  const now = Date.now();
  let cache = globalForTokenCache.voteTokenCache;

  if (!cache || cache.expiresAt < now) {
    const byToken = await loadTokenIndex(db);
    cache = { byToken, expiresAt: now + CACHE_TTL_MS };
    globalForTokenCache.voteTokenCache = cache;
  }

  return cache.byToken.get(token) ?? null;
}
