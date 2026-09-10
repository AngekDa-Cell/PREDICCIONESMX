// Queries para la BD de votos
//
// API:
// - recordVote({fixtureId, clientHash, pick, ipPrefix, uaFingerprint})
//   → {ok: true, vote: CrowdSummary} | {ok: false, reason: 'duplicate'|'invalid'}
// - getCrowdSummary(fixtureId)
//   → CrowdSummary | null (null si no hay votos)
// - getUserPick(fixtureId, clientHash) → 'home'|'draw'|'away'|null
// - getCrowdDelta(fixtureId) → {home, draw, away}  (delta 1X2 desde crowd)

import { votesDb } from "./votes-client";

export type Pick = "home" | "draw" | "away";

export interface CrowdSummary {
  fixture_id: number;
  home: number;
  draw: number;
  away: number;
  total: number;
  home_pct: number;
  draw_pct: number;
  away_pct: number;
  first_vote_at: string | null;
  last_vote_at: string | null;
}

export type VoteResult =
  | { ok: true; summary: CrowdSummary }
  | {
      ok: false;
      reason: "duplicate" | "invalid" | "db_error";
      existing_pick?: Pick;
      summary?: CrowdSummary;
    };

function isValidPick(p: unknown): p is Pick {
  return p === "home" || p === "draw" || p === "away";
}

function recomputeSummary(fixtureId: number): CrowdSummary {
  const row = votesDb
    .prepare(
      `SELECT
        COALESCE(SUM(CASE WHEN pick='home' THEN 1 ELSE 0 END), 0) AS home,
        COALESCE(SUM(CASE WHEN pick='draw' THEN 1 ELSE 0 END), 0) AS draw,
        COALESCE(SUM(CASE WHEN pick='away' THEN 1 ELSE 0 END), 0) AS away,
        COUNT(*) AS total,
        MIN(created_at) AS first_vote_at,
        MAX(created_at) AS last_vote_at
       FROM votes WHERE fixture_id = ?`,
    )
    .get(fixtureId) as {
      home: number;
      draw: number;
      away: number;
      total: number;
      first_vote_at: string | null;
      last_vote_at: string | null;
    };

  const total = row.total || 0;
  const safeDiv = (n: number) => (total > 0 ? n / total : 0);

  return {
    fixture_id: fixtureId,
    home: row.home || 0,
    draw: row.draw || 0,
    away: row.away || 0,
    total,
    home_pct: safeDiv(row.home || 0),
    draw_pct: safeDiv(row.draw || 0),
    away_pct: safeDiv(row.away || 0),
    first_vote_at: row.first_vote_at,
    last_vote_at: row.last_vote_at,
  };
}

export function recordVote(input: {
  fixtureId: number;
  clientHash: string;
  pick: unknown;
  ipPrefix?: string;
  uaFingerprint?: string;
}): VoteResult {
  if (!isValidPick(input.pick)) return { ok: false, reason: "invalid" };
  if (!input.clientHash || input.clientHash.length < 8) {
    return { ok: false, reason: "invalid" };
  }

  try {
    const existing = votesDb
      .prepare(`SELECT pick FROM votes WHERE fixture_id=? AND client_hash=?`)
      .get(input.fixtureId, input.clientHash) as { pick: Pick } | undefined;

    if (existing) {
      const summary = recomputeSummary(input.fixtureId);
      return {
        ok: false,
        reason: "duplicate",
        existing_pick: existing.pick,
        summary,
      };
    }

    const tx = votesDb.transaction(() => {
      votesDb
        .prepare(
          `INSERT INTO votes (fixture_id, client_hash, pick, ip_prefix, ua_fingerprint)
           VALUES (?, ?, ?, ?, ?)`,
        )
        .run(
          input.fixtureId,
          input.clientHash,
          input.pick,
          input.ipPrefix ?? null,
          input.uaFingerprint ?? null,
        );

      // upsert meta
      votesDb
        .prepare(
          `INSERT INTO vote_meta (fixture_id, first_vote_at, last_vote_at, vote_count)
           VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
           ON CONFLICT(fixture_id) DO UPDATE SET
             last_vote_at = CURRENT_TIMESTAMP,
             vote_count = vote_count + 1`,
        )
        .run(input.fixtureId);
    });
    tx();

    return { ok: true, summary: recomputeSummary(input.fixtureId) };
  } catch (err) {
    console.error("[votes] recordVote error:", err);
    return { ok: false, reason: "db_error" };
  }
}

export function getCrowdSummary(fixtureId: number): CrowdSummary | null {
  try {
    const summary = recomputeSummary(fixtureId);
    if (summary.total === 0) return null;
    return summary;
  } catch (err) {
    console.error("[votes] getCrowdSummary error:", err);
    return null;
  }
}

export function getUserPick(
  fixtureId: number,
  clientHash: string,
): Pick | null {
  if (!clientHash) return null;
  const row = votesDb
    .prepare(`SELECT pick FROM votes WHERE fixture_id=? AND client_hash=?`)
    .get(fixtureId, clientHash) as { pick: Pick } | undefined;
  return row?.pick ?? null;
}

/**
 * Devuelve el crowd pick: el 1X2 con más votos (no la moda en empate,
 * sino null si hay empate para no sesgar).
 */
export function getCrowdPick(
  summary: CrowdSummary,
): Pick | "tie" | null {
  if (summary.total === 0) return null;
  const max = Math.max(summary.home, summary.draw, summary.away);
  const leaders = [
    summary.home === max ? "home" : null,
    summary.draw === max ? "draw" : null,
    summary.away === max ? "away" : null,
  ].filter(Boolean) as Pick[];
  if (leaders.length > 1) return "tie";
  return leaders[0];
}

// ─────────────────────────────────────────────────────────────────────────────
// QUINIELA BATCH — usado por /api/quiniela (vista /partidos)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Devuelve los picks actuales de un votante para varios fixtures en una sola query.
 * Devuelve un Map<fixture_id, pick> con solo los fixtures donde el votante votó.
 */
export function getUserPicksBatch(
  fixtureIds: number[],
  clientHash: string,
): Map<number, Pick> {
  const out = new Map<number, Pick>();
  if (!clientHash || fixtureIds.length === 0) return out;
  try {
    const placeholders = fixtureIds.map(() => "?").join(",");
    const rows = votesDb
      .prepare(
        `SELECT fixture_id, pick FROM votes
         WHERE client_hash = ? AND fixture_id IN (${placeholders})`,
      )
      .all(clientHash, ...fixtureIds) as { fixture_id: number; pick: Pick }[];
    for (const r of rows) out.set(r.fixture_id, r.pick);
  } catch (err) {
    console.error("[votes] getUserPicksBatch error:", err);
  }
  return out;
}

export interface BatchVoteInput {
  fixtureId: number;
  pick: Pick;
}

export interface BatchVoteResultItem {
  fixture_id: number;
  pick: Pick;
  status: "saved" | "updated";  // saved = nuevo voto, updated = cambió pick
}

export interface BatchVoteResult {
  ok: true;
  saved: BatchVoteResultItem[];
  summaries: Record<number, CrowdSummary>;  // fixture_id → summary
}

/**
 * Inserta/actualiza múltiples votos en una sola transacción.
 * Usa INSERT ... ON CONFLICT DO UPDATE para permitir editar picks existentes
 * del mismo votante (mientras la jornada no haya empezado).
 *
 * Devuelve por cada fixture si fue `saved` (nuevo) o `updated` (cambio).
 */
export function recordVotesBatch(input: {
  votes: BatchVoteInput[];
  clientHash: string;
  ipPrefix?: string;
  uaFingerprint?: string;
}): BatchVoteResult | { ok: false; reason: "invalid" | "db_error" } {
  if (!input.clientHash || input.clientHash.length < 8) {
    return { ok: false, reason: "invalid" };
  }
  for (const v of input.votes) {
    if (!isValidPick(v.pick)) return { ok: false, reason: "invalid" };
  }
  if (input.votes.length === 0) {
    return { ok: true, saved: [], summaries: {} };
  }

  try {
    const findExisting = votesDb.prepare(
      `SELECT pick FROM votes WHERE fixture_id = ? AND client_hash = ?`,
    );
    const upsertVote = votesDb.prepare(
      `INSERT INTO votes (fixture_id, client_hash, pick, ip_prefix, ua_fingerprint)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(fixture_id, client_hash) DO UPDATE SET
         pick = excluded.pick,
         ip_prefix = excluded.ip_prefix,
         ua_fingerprint = excluded.ua_fingerprint`,
    );
    const upsertMeta = votesDb.prepare(
      `INSERT INTO vote_meta (fixture_id, first_vote_at, last_vote_at, vote_count)
       VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
       ON CONFLICT(fixture_id) DO UPDATE SET
         last_vote_at = CURRENT_TIMESTAMP,
         vote_count = vote_count + 1`,
    );

    const saved: BatchVoteResultItem[] = [];
    const summaries: Record<number, CrowdSummary> = {};

    const tx = votesDb.transaction(() => {
      for (const v of input.votes) {
        const existing = findExisting.get(v.fixtureId, input.clientHash) as
          | { pick: Pick }
          | undefined;
        const status: "saved" | "updated" = existing ? "updated" : "saved";
        upsertVote.run(
          v.fixtureId,
          input.clientHash,
          v.pick,
          input.ipPrefix ?? null,
          input.uaFingerprint ?? null,
        );
        upsertMeta.run(v.fixtureId);
        saved.push({ fixture_id: v.fixtureId, pick: v.pick, status });
      }
    });
    tx();

    // Recompute summaries fuera de la TX (no afecta atomicidad, pero es más limpio)
    for (const v of input.votes) {
      summaries[v.fixtureId] = recomputeSummary(v.fixtureId);
    }

    return { ok: true, saved, summaries };
  } catch (err) {
    console.error("[votes] recordVotesBatch error:", err);
    return { ok: false, reason: "db_error" };
  }
}
