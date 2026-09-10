// API para registrar votos de la banda.
//
// POST /api/votes/[token]  body: {pick: 'home'|'draw'|'away'}
//   - Crea cookie client_hash si no existe
//   - Inserta voto (unique constraint por fixture_id + client_hash)
//   - Devuelve summary actualizado
//
// GET /api/votes/[token]
//   - Devuelve el summary actual + el pick del cliente si ya votó
//
// El client_hash se deriva de cookie + (ip_prefix + UA fingerprint) hasheados.
// Nunca guardamos IPs crudas ni UA completas.

import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import { db as mainDb } from "@/lib/db/client";
import { isValidToken, resolveTokenAsync } from "@/lib/votes/token";
import {
  getCrowdSummary,
  getUserPick,
  recordVote,
  type Pick,
} from "@/lib/db/votes";

const CLIENT_COOKIE = "votante_id";
const VOTED_COOKIE = "votante_quinc_v1";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 180; // 180 días
const VOTED_COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 año

function hashClientId(opts: { ipPrefix?: string; ua?: string }): string {
  const h = crypto.createHash("sha256");
  h.update("votante:");
  if (opts.ipPrefix) h.update(opts.ipPrefix);
  if (opts.ua) h.update(opts.ua);
  return h.digest("hex").slice(0, 32);
}

function getClientIpPrefix(req: NextRequest): string | undefined {
  const xff = req.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0].trim();
  const real = req.headers.get("x-real-ip");
  if (real) return real.trim();
  return undefined;
}

async function getOrCreateClientHash(
  req: NextRequest,
): Promise<{ hash: string; createdCookie: boolean; cookie: string }> {
  const cookieStore = cookies();
  let cookie = cookieStore.get(CLIENT_COOKIE)?.value;
  let createdCookie = false;
  if (!cookie) {
    cookie = crypto.randomBytes(16).toString("hex");
    createdCookie = true;
  }
  const ip = getClientIpPrefix(req);
  const ua = req.headers.get("user-agent") ?? "";
  const envHash = hashClientId({ ipPrefix: ip, ua });
  const finalHash = crypto
    .createHash("sha256")
    .update(cookie + ":" + envHash)
    .digest("hex")
    .slice(0, 32);
  return { hash: finalHash, createdCookie, cookie };
}

export async function GET(
  req: NextRequest,
  ctx: { params: { token: string } },
) {
  const token = ctx.params.token;
  if (!isValidToken(token)) {
    return NextResponse.json({ error: "invalid_token" }, { status: 404 });
  }
  const fixtureId = await resolveTokenAsync(token, mainDb);
  if (fixtureId === null) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }

  const { hash, createdCookie, cookie } = await getOrCreateClientHash(req);
  const summary = getCrowdSummary(fixtureId);
  const userPick = getUserPick(fixtureId, hash);

  const res = NextResponse.json({
    ok: true,
    fixture_id: fixtureId,
    summary,
    user_pick: userPick,
  });
  if (createdCookie) {
    res.cookies.set(CLIENT_COOKIE, cookie, {
      maxAge: COOKIE_MAX_AGE,
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure: process.env.NODE_ENV === "production",
    });
  }
  return res;
}

export async function POST(
  req: NextRequest,
  ctx: { params: { token: string } },
) {
  const token = ctx.params.token;
  if (!isValidToken(token)) {
    return NextResponse.json({ error: "invalid_token" }, { status: 404 });
  }
  const fixtureId = await resolveTokenAsync(token, mainDb);
  if (fixtureId === null) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }

  let body: { pick?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  if (
    typeof body.pick !== "string" ||
    !["home", "draw", "away"].includes(body.pick)
  ) {
    return NextResponse.json({ error: "invalid_pick" }, { status: 400 });
  }

  const { hash, createdCookie, cookie } = await getOrCreateClientHash(req);
  const ip = getClientIpPrefix(req);
  const ua = req.headers.get("user-agent") ?? "";

  const result = recordVote({
    fixtureId,
    clientHash: hash,
    pick: body.pick as Pick,
    ipPrefix: ip,
    uaFingerprint: ua
      ? crypto.createHash("md5").update(ua).digest("hex").slice(0, 16)
      : undefined,
  });

  const baseCookieOpts = {
    maxAge: COOKIE_MAX_AGE,
    httpOnly: true,
    sameSite: "lax" as const,
    path: "/",
    secure: process.env.NODE_ENV === "production",
  };

  if (!result.ok && result.reason === "invalid") {
    return NextResponse.json({ error: "invalid" }, { status: 400 });
  }
  if (!result.ok && result.reason === "db_error") {
    return NextResponse.json({ error: "db_error" }, { status: 500 });
  }
  if (!result.ok && result.reason === "duplicate") {
    const res = NextResponse.json({
      ok: true,
      already_voted: true,
      existing_pick: result.existing_pick,
      summary: result.summary,
    });
    if (createdCookie) {
      res.cookies.set(CLIENT_COOKIE, cookie, baseCookieOpts);
    }
    return res;
  }

  const okResult = result as { ok: true; summary: any };
  const res = NextResponse.json({
    ok: true,
    already_voted: false,
    pick: body.pick,
    summary: okResult.summary,
  });
  if (createdCookie) {
    res.cookies.set(CLIENT_COOKIE, cookie, baseCookieOpts);
  }
  res.cookies.set(VOTED_COOKIE, "1", {
    maxAge: VOTED_COOKIE_MAX_AGE,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure: process.env.NODE_ENV === "production",
  });
  return res;
}

export const dynamic = "force-dynamic";
