// API para guardar quinielas batch por jornada.
//
// POST /api/quiniela
//   body: {
//     jornada: { season_id: number, matchday: number },
//     picks: { fixture_id: number, pick: 'home'|'draw'|'away' }[]
//   }
//
// Comportamiento:
//   - Valida que TODOS los fixture_id correspondan a (season_id, matchday)
//     y que aún no hayan empezado (starting_at > now)
//   - Usa el mismo client_hash que /api/votes/[token] (cookie compartida)
//   - Transaccional: si falla algo, rollback completo
//   - Devuelve: { ok, saved: [{fixture_id, pick, status}], summaries }
//
// GET /api/quiniela?season_id=&matchday=
//   - Devuelve los picks del votante para una jornada dada
//   - Útil para que el componente cliente pre-cargue el estado

import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { db as mainDb } from "@/lib/db/client";
import {
  getUserPicksBatch,
  recordVotesBatch,
  getCrowdSummary,
  type Pick,
  type CrowdSummary,
} from "@/lib/db/votes";
import {
  getOrCreateClientIdentity,
  COOKIE_OPTIONS,
  CLIENT_COOKIE,
  VOTED_COOKIE,
  VOTED_COOKIE_OPTIONS,
} from "@/lib/votes/client-hash";

interface PostBody {
  jornada?: { season_id?: number; matchday?: number };
  picks?: { fixture_id?: number; pick?: string }[];
}

function isValidBody(body: PostBody): {
  ok: true;
  seasonId: number;
  matchday: number;
  picks: { fixtureId: number; pick: Pick }[];
} | { ok: false; error: string } {
  if (!body.jornada) return { ok: false, error: "missing_jornada" };
  const sid = body.jornada.season_id;
  const md = body.jornada.matchday;
  if (typeof sid !== "number" || typeof md !== "number") {
    return { ok: false, error: "invalid_jornada" };
  }
  if (!Array.isArray(body.picks)) return { ok: false, error: "missing_picks" };
  const picks: { fixtureId: number; pick: Pick }[] = [];
  for (const p of body.picks) {
    if (typeof p.fixture_id !== "number") return { ok: false, error: "invalid_fixture_id" };
    if (p.pick !== "home" && p.pick !== "draw" && p.pick !== "away") {
      return { ok: false, error: "invalid_pick" };
    }
    picks.push({ fixtureId: p.fixture_id, pick: p.pick });
  }
  return { ok: true, seasonId: sid, matchday: md, picks };
}

export async function POST(req: NextRequest) {
  let body: PostBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const v = isValidBody(body);
  if (!v.ok) {
    return NextResponse.json({ error: v.error }, { status: 400 });
  }

  // Verificar que los fixture_ids correspondan a la jornada y aún no hayan empezado
  if (v.picks.length > 0) {
    const ids = v.picks.map((p) => p.fixtureId);
    const placeholders = ids.map(() => "?").join(",");
    const rows = mainDb
      .prepare(
        `SELECT id, season_id, matchday, starting_at, home_score
         FROM fixtures
         WHERE id IN (${placeholders})`,
      )
      .all(...ids) as {
      id: number;
      season_id: number | null;
      matchday: number | null;
      starting_at: string;
      home_score: number | null;
    }[];

    if (rows.length !== ids.length) {
      return NextResponse.json(
        { error: "some_fixtures_not_found" },
        { status: 400 },
      );
    }

    const nowMs = Date.now();
    for (const row of rows) {
      if (row.season_id !== v.seasonId || row.matchday !== v.matchday) {
        return NextResponse.json(
          { error: "fixture_jornada_mismatch", fixture_id: row.id },
          { status: 400 },
        );
      }
      const startMs = new Date(row.starting_at).getTime();
      if (startMs <= nowMs) {
        return NextResponse.json(
          { error: "fixture_already_started", fixture_id: row.id },
          { status: 400 },
        );
      }
      if (row.home_score !== null) {
        return NextResponse.json(
          { error: "fixture_already_finished", fixture_id: row.id },
          { status: 400 },
        );
      }
    }
  }

  // Identidad del votante (compartida con /api/votes/[token])
  const identity = getOrCreateClientIdentity(req);

  // Guardar en batch (transaccional)
  const result = recordVotesBatch({
    votes: v.picks,
    clientHash: identity.hash,
    ipPrefix: identity.ipPrefix,
    uaFingerprint: identity.uaFingerprint,
  });

  if (!result.ok) {
    if (result.reason === "invalid") {
      return NextResponse.json({ error: "invalid" }, { status: 400 });
    }
    return NextResponse.json({ error: "db_error" }, { status: 500 });
  }

  const res = NextResponse.json({
    ok: true,
    saved: result.saved,
    summaries: result.summaries,
  });
  if (identity.createdCookie) {
    res.cookies.set(CLIENT_COOKIE, identity.cookie, COOKIE_OPTIONS);
  }
  // Marca al usuario como "ya votó" — activa la revelación de % crowd
  // en futuras visitas a /votacion.
  res.cookies.set(VOTED_COOKIE, "1", VOTED_COOKIE_OPTIONS);
  return res;
}

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const seasonId = Number(url.searchParams.get("season_id"));
  const matchday = Number(url.searchParams.get("matchday"));
  if (!Number.isFinite(seasonId) || !Number.isFinite(matchday)) {
    return NextResponse.json({ error: "invalid_jornada" }, { status: 400 });
  }

  const identity = getOrCreateClientIdentity(req);

  // Traer fixture_ids de la jornada
  const rows = mainDb
    .prepare(
      `SELECT id FROM fixtures
       WHERE season_id = ? AND matchday = ? AND league_id = 743
         AND home_score IS NULL AND starting_at > datetime('now')
       ORDER BY starting_at ASC`,
    )
    .all(seasonId, matchday) as { id: number }[];

  const fixtureIds = rows.map((r) => r.id);
  const picks = getUserPicksBatch(fixtureIds, identity.hash);

  // Opcional: incluir crowd summaries si el cliente lo pide
  const includeSummaries = url.searchParams.get("summaries") === "1";
  let summaries: Record<number, CrowdSummary> | undefined;
  if (includeSummaries) {
    summaries = {};
    for (const id of fixtureIds) {
      const s = getCrowdSummary(id);
      if (s) summaries[id] = s;
    }
  }

  const res = NextResponse.json({
    ok: true,
    picks: Object.fromEntries(picks), // {fixture_id_str: pick}
    ...(summaries ? { summaries } : {}),
  });
  if (identity.createdCookie) {
    res.cookies.set(CLIENT_COOKIE, identity.cookie, COOKIE_OPTIONS);
  }
  return res;
}

export const dynamic = "force-dynamic";