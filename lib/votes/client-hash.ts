// Helper compartido para derivar client_hash de un request.
//
// Esquema:
//   client_hash = sha256(cookie + ":" + sha256("votante:" + ipPrefix + ":" + ua))[:32]
//
// Se usa tanto en /api/votes/[token] como en /api/quiniela para que un votante
// tenga el MISMO hash en ambos endpoints. Esto garantiza que:
// - Si el usuario vota partido-por-partido (links compartidos) y luego vota
//   toda la quiniela en batch, los picks se identifican como del mismo votante.
// - Si primero llena la quiniela y luego edita desde un link, también.
//
// Componentes:
// - COOKIE votante_id (HttpOnly, SameSite=Lax, 180d)
// - ipPrefix: primera IP de X-Forwarded-For o X-Real-IP
// - ua fingerprint: primeros 16 chars de md5(user-agent)
//
// No guardamos IPs crudas ni UAs completas en la BD, solo fingerprints.

import crypto from "crypto";
import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

export const CLIENT_COOKIE = "votante_id";
export const COOKIE_MAX_AGE = 60 * 60 * 24 * 180; // 180 días

// Cookie "ligera" para indicar que el usuario YA VOTÓ al menos una vez.
// Se setea en POST /api/quiniela y POST /api/votes/[token] cuando el voto
// se guarda exitosamente. No requiere cómputo de hash — basta con que exista
// en el request del usuario para que el server component decida si mostrar
// los % crowd (los revelamos solo después de la primera votación).
// Esta cookie existe para evitar el problema de hash mismatch entre
// server component (sin IP/UA) y route handler (con IP/UA completos).
export const VOTED_COOKIE = "votante_quinc_v1";
export const VOTED_COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 año

export function hashEnv(ipPrefix?: string, ua?: string): string {
  const h = crypto.createHash("sha256");
  h.update("votante:");
  if (ipPrefix) h.update(ipPrefix);
  if (ua) h.update(ua);
  return h.digest("hex").slice(0, 32);
}

export function finalHash(cookie: string, envHash: string): string {
  return crypto
    .createHash("sha256")
    .update(`${cookie}:${envHash}`)
    .digest("hex")
    .slice(0, 32);
}

export function getClientIpPrefix(req: NextRequest): string | undefined {
  const xff = req.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0].trim();
  const real = req.headers.get("x-real-ip");
  if (real) return real.trim();
  return undefined;
}

export function fingerprintUa(ua: string | null | undefined): string | undefined {
  if (!ua) return undefined;
  return crypto.createHash("md5").update(ua).digest("hex").slice(0, 16);
}

export interface ClientIdentity {
  hash: string;
  cookie: string;
  createdCookie: boolean;
  ipPrefix?: string;
  uaFingerprint?: string;
}

/**
 * Lee o crea la cookie `votante_id` y deriva el client_hash completo.
 * Si la cookie no existe, la crea (devuelve createdCookie=true para que
 * el caller la setee en la response).
 *
 * @param req NextRequest (route handler) o undefined (server component)
 */
export function getOrCreateClientIdentity(
  req?: NextRequest,
): ClientIdentity {
  const cookieStore = cookies();
  let cookie = cookieStore.get(CLIENT_COOKIE)?.value;
  let createdCookie = false;
  if (!cookie) {
    cookie = crypto.randomBytes(16).toString("hex");
    createdCookie = true;
  }
  const ipPrefix = req ? getClientIpPrefix(req) : undefined;
  const ua = req?.headers.get("user-agent") ?? "";
  const envHash = hashEnv(ipPrefix, ua);
  const hash = finalHash(cookie, envHash);
  return { hash, cookie, createdCookie, ipPrefix, uaFingerprint: fingerprintUa(ua) };
}

/**
 * Opciones de cookie listas para usar en NextResponse.cookies.set().
 */
export const COOKIE_OPTIONS = {
  maxAge: COOKIE_MAX_AGE,
  httpOnly: true,
  sameSite: "lax" as const,
  path: "/",
  secure: process.env.NODE_ENV === "production",
};

export const VOTED_COOKIE_OPTIONS = {
  maxAge: VOTED_COOKIE_MAX_AGE,
  httpOnly: true,
  sameSite: "lax" as const,
  path: "/",
  secure: process.env.NODE_ENV === "production",
};