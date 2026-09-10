// Queries de fixtures

import { db } from "./client";
import { getMatchdayOrdinalByDate } from "./matchday";
import type {
  FixtureWithTeams,
  FixtureDetail,
  TeamFixture,
  FixtureWithPrediction,
  PredictionView,
  AnalystPrediction,
  deriveOutcome,
} from "./types";

const PREDICTION_JOIN = `
  LEFT JOIN (
    SELECT ap1.* FROM analyst_predictions ap1
    INNER JOIN (
      SELECT fixture_id, MAX(created_at) AS max_created
      FROM analyst_predictions GROUP BY fixture_id
    ) ap2 ON ap1.fixture_id = ap2.fixture_id AND ap1.created_at = ap2.max_created
  ) p ON p.fixture_id = f.id
`;

function mapPrediction(r: Record<string, unknown>): PredictionView | null {
  if (!r.p_id) return null;
  const outcome = (r.p_most_likely_score
    ? (() => {
        const m = String(r.p_most_likely_score).match(/^(\d+)-(\d+)$/);
        if (!m) return null;
        const hg = parseInt(m[1], 10);
        const ag = parseInt(m[2], 10);
        if (hg > ag) return 'home_win';
        if (hg < ag) return 'away_win';
        return 'draw';
      })()
    : null) as string | null;
  return {
    id: r.p_id as number,
    fixture_id: r.p_fixture_id as number,
    home_win: r.p_home_win as number | null,
    draw: r.p_draw as number | null,
    away_win: r.p_away_win as number | null,
    confidence: r.p_confidence as number | null,
    predicted_home_goals: r.p_predicted_home_goals as number | null,
    predicted_away_goals: r.p_predicted_away_goals as number | null,
    most_likely_score: r.p_most_likely_score as string | null,
    key_factors: r.p_key_factors as string | null,
    contrarian_view: r.p_contrarian_view as string | null,
    derby_flag: r.p_derby_flag as number | null,
    derby_name: r.p_derby_name as string | null,
    created_at: r.p_created_at as string | null,
    is_backtest: r.p_is_backtest as number | null,
    predicted_outcome: outcome,
    home_win_prob: r.p_home_win as number | null,
    draw_prob: r.p_draw as number | null,
    away_win_prob: r.p_away_win as number | null,
  };
}

const BASE_FIXTURE_COLS = `
  f.id, f.season_id, f.league_id, f.venue_id,
  f.home_team_id, f.away_team_id, f.starting_at, f.state, f.round, f.matchday,
  f.home_score, f.away_score, f.home_ht_score, f.away_ht_score, f.attendance,
  ht.name AS home_team_name, ht.short_code AS home_team_short,
  ht.logo_url AS home_team_logo,
  ht.primary_color AS home_team_primary_color,
  ht.secondary_color AS home_team_secondary_color,
  at.name AS away_team_name, at.short_code AS away_team_short,
  at.logo_url AS away_team_logo,
  at.primary_color AS away_team_primary_color,
  at.secondary_color AS away_team_secondary_color,
  v.name AS venue_name, v.city AS venue_city
`;

const PRED_COLS = `
  p.id AS p_id, p.fixture_id AS p_fixture_id,
  p.home_win AS p_home_win, p.draw AS p_draw, p.away_win AS p_away_win,
  p.confidence AS p_confidence,
  p.predicted_home_goals AS p_predicted_home_goals,
  p.predicted_away_goals AS p_predicted_away_goals,
  p.most_likely_score AS p_most_likely_score,
  p.key_factors AS p_key_factors,
  p.contrarian_view AS p_contrarian_view,
  p.derby_flag AS p_derby_flag, p.derby_name AS p_derby_name,
  p.created_at AS p_created_at, p.is_backtest AS p_is_backtest
`;

/**
 * Partidos próximos con predicción (para cards del home / partidos).
 */
export function getUpcomingFixtures(
  days = 7,
  limit = 30,
): FixtureWithPrediction[] {
  const stmt = db.prepare(`
    SELECT ${BASE_FIXTURE_COLS}, ${PRED_COLS}
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    ${PREDICTION_JOIN.replace("p.", "p.")}
    WHERE f.league_id = 743
      AND f.home_score IS NULL
      AND f.starting_at >= datetime('now')
      AND f.starting_at <= datetime('now', '+${days} days')
    ORDER BY f.starting_at ASC
    LIMIT ?
  `);
  const rows = stmt.all(limit) as Record<string, unknown>[];
  return rows.map((r) => ({
    id: r.id as number,
    season_id: r.season_id as number | null,
    league_id: r.league_id as number,
    venue_id: r.venue_id as number | null,
    home_team_id: r.home_team_id as number,
    away_team_id: r.away_team_id as number,
    starting_at: r.starting_at as string,
    state: r.state as string | null,
    round: r.round as string | null,
    matchday: r.matchday as number | null,
    home_score: r.home_score as number | null,
    away_score: r.away_score as number | null,
    home_ht_score: r.home_ht_score as number | null,
    away_ht_score: r.away_ht_score as number | null,
    attendance: r.attendance as number | null,
    home_team_name: r.home_team_name as string,
    home_team_short: r.home_team_short as string | null,
    home_team_logo: r.home_team_logo as string | null,
    home_team_primary_color: r.home_team_primary_color as string | null,
    home_team_secondary_color: r.home_team_secondary_color as string | null,
    away_team_name: r.away_team_name as string,
    away_team_short: r.away_team_short as string | null,
    away_team_logo: r.away_team_logo as string | null,
    away_team_primary_color: r.away_team_primary_color as string | null,
    away_team_secondary_color: r.away_team_secondary_color as string | null,
    venue_name: r.venue_name as string | null,
    venue_city: r.venue_city as string | null,
    prediction: mapPrediction(r),
  }));
}

/**
 * Detalle de un fixture por ID.
 */
export function getFixtureById(id: number): FixtureDetail | null {
  const stmt = db.prepare(`
    SELECT
      ${BASE_FIXTURE_COLS},
      v.altitude_m AS venue_altitude_m,
      v.capacity AS venue_capacity,
      s.name AS season_name
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    LEFT JOIN seasons s ON s.id = f.season_id
    WHERE f.id = ?
  `);
  return stmt.get(id) as FixtureDetail | null;
}

/**
 * Últimos N partidos terminados (para equipo y home).
 */
export function getRecentFixtures(limit = 5): FixtureWithTeams[] {
  const stmt = db.prepare(`
    SELECT ${BASE_FIXTURE_COLS}
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    WHERE f.league_id = 743
      AND f.home_score IS NOT NULL
      AND f.starting_at < datetime('now')
    ORDER BY f.starting_at DESC
    LIMIT ?
  `);
  return stmt.all(limit) as FixtureWithTeams[];
}

/**
 * Fixture por jornada (próximos 60 días).
 */
export function getFixturesByJornada(
  days = 60,
): Record<number, FixtureWithTeams[]> {
  const stmt = db.prepare(`
    SELECT ${BASE_FIXTURE_COLS}
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    WHERE f.league_id = 743
      AND f.starting_at >= datetime('now')
      AND f.starting_at <= datetime('now', '+${days} days')
    ORDER BY f.starting_at ASC
  `);
  const rows = stmt.all() as FixtureWithTeams[];
  const byJornada: Record<number, FixtureWithTeams[]> = {};
  for (const f of rows) {
    const j = getMatchdayOrdinalByDate(f.season_id, f.matchday, f.starting_at) ?? 0;
    (byJornada[j] ??= []).push(f);
  }
  return byJornada;
}

/**
 * Fixtures en un rango de fechas arbitrario (para vista calendario).
 * Retorna filas ordenadas cronológicamente.
 */
export function getFixturesInRange(
  startISO: string, // 'YYYY-MM-DD'
  endISO: string,   // 'YYYY-MM-DD' (inclusivo)
  leagueId = 743,
): FixtureWithPrediction[] {
  const stmt = db.prepare(`
    SELECT ${BASE_FIXTURE_COLS}, ${PRED_COLS}
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    ${PREDICTION_JOIN}
    WHERE f.league_id = ${leagueId}
      AND date(f.starting_at) >= date(?)
      AND date(f.starting_at) <= date(?)
    ORDER BY f.starting_at ASC
  `);
  const rows = stmt.all(startISO, endISO) as Record<string, unknown>[];
  return rows.map((r) => ({
    id: r.id as number,
    season_id: r.season_id as number | null,
    league_id: r.league_id as number,
    venue_id: r.venue_id as number | null,
    home_team_id: r.home_team_id as number,
    away_team_id: r.away_team_id as number,
    starting_at: r.starting_at as string,
    state: r.state as string | null,
    round: r.round as string | null,
    matchday: r.matchday as number | null,
    home_score: r.home_score as number | null,
    away_score: r.away_score as number | null,
    home_ht_score: r.home_ht_score as number | null,
    away_ht_score: r.away_ht_score as number | null,
    attendance: r.attendance as number | null,
    home_team_name: r.home_team_name as string,
    home_team_short: r.home_team_short as string | null,
    home_team_logo: r.home_team_logo as string | null,
    home_team_primary_color: r.home_team_primary_color as string | null,
    home_team_secondary_color: r.home_team_secondary_color as string | null,
    away_team_name: r.away_team_name as string,
    away_team_short: r.away_team_short as string | null,
    away_team_logo: r.away_team_logo as string | null,
    away_team_primary_color: r.away_team_primary_color as string | null,
    away_team_secondary_color: r.away_team_secondary_color as string | null,
    venue_name: r.venue_name as string | null,
    venue_city: r.venue_city as string | null,
    prediction: mapPrediction(r),
  }));
}

/**
 * Partidos terminados con predicción (para resultados).
 */
export function getRecentFinishedWithPredictions(
  limit = 6,
): FixtureWithPrediction[] {
  const stmt = db.prepare(`
    SELECT ${BASE_FIXTURE_COLS}, ${PRED_COLS}
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    ${PREDICTION_JOIN}
    WHERE f.league_id = 743
      AND f.home_score IS NOT NULL
      AND f.starting_at < datetime('now')
    ORDER BY f.starting_at DESC
    LIMIT ?
  `);
  const rows = stmt.all(limit) as Record<string, unknown>[];
  return rows.map((r) => ({
    id: r.id as number,
    season_id: r.season_id as number | null,
    league_id: r.league_id as number,
    venue_id: r.venue_id as number | null,
    home_team_id: r.home_team_id as number,
    away_team_id: r.away_team_id as number,
    starting_at: r.starting_at as string,
    state: r.state as string | null,
    round: r.round as string | null,
    matchday: r.matchday as number | null,
    home_score: r.home_score as number | null,
    away_score: r.away_score as number | null,
    home_ht_score: r.home_ht_score as number | null,
    away_ht_score: r.away_ht_score as number | null,
    attendance: r.attendance as number | null,
    home_team_name: r.home_team_name as string,
    home_team_short: r.home_team_short as string | null,
    home_team_logo: r.home_team_logo as string | null,
    home_team_primary_color: r.home_team_primary_color as string | null,
    home_team_secondary_color: r.home_team_secondary_color as string | null,
    away_team_name: r.away_team_name as string,
    away_team_short: r.away_team_short as string | null,
    away_team_logo: r.away_team_logo as string | null,
    away_team_primary_color: r.away_team_primary_color as string | null,
    away_team_secondary_color: r.away_team_secondary_color as string | null,
    venue_name: r.venue_name as string | null,
    venue_city: r.venue_city as string | null,
    prediction: mapPrediction(r),
  }));
}

// ─────────────────────────────────────────────────────────────────────────────
// QUINIELA — queries específicas para /partidos (vista de votación batch)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Devuelve todas las jornadas futuras (con partidos sin empezar) en Liga MX,
 * con el ordinal humano calculado y ordenadas por fecha del primer partido.
 */
export interface JornadaOption {
  season_id: number;
  matchday: number;
  ordinal: number;
  label: string;
  first_kickoff: string;
  match_count: number;
  has_started: boolean;
}

export function getUpcomingJornadas(days = 180): JornadaOption[] {
  const rows = db
    .prepare(
      `SELECT season_id, matchday,
              MIN(starting_at) AS first_kickoff,
              MAX(starting_at) AS last_kickoff,
              COUNT(*) AS n,
              MIN(CASE WHEN starting_at <= datetime('now') THEN 1 ELSE 0 END) AS has_started_flag
       FROM fixtures
       WHERE league_id = 743
         AND home_score IS NULL
         AND starting_at <= datetime('now', '+${days} days')
       GROUP BY season_id, matchday
       ORDER BY first_kickoff ASC`,
    )
    .all() as {
      season_id: number;
      matchday: number;
      first_kickoff: string;
      last_kickoff: string;
      n: number;
      has_started_flag: number;
    }[];

  return rows.map((r) => {
    const ordinal =
      getMatchdayOrdinalByDate(r.season_id, r.matchday, r.first_kickoff) ?? 0;
    return {
      season_id: r.season_id,
      matchday: r.matchday,
      ordinal,
      label: ordinal > 0 ? `J${ordinal}` : `MD ${r.matchday}`,
      first_kickoff: r.first_kickoff,
      match_count: r.n,
      has_started: r.has_started_flag === 1,
    };
  });
}

/**
 * Devuelve los partidos de una jornada específica (season_id + matchday) en Liga MX.
 * Solo partidos sin empezar (home_score IS NULL). Incluye prediction.
 */
export function getFixturesByJornadaExact(
  seasonId: number,
  matchday: number,
): FixtureWithPrediction[] {
  const stmt = db.prepare(`
    SELECT ${BASE_FIXTURE_COLS}, ${PRED_COLS}
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    ${PREDICTION_JOIN}
    WHERE f.league_id = 743
      AND f.season_id = ?
      AND f.matchday = ?
    ORDER BY f.starting_at ASC
  `);
  const rows = stmt.all(seasonId, matchday) as Record<string, unknown>[];
  return rows.map((r) => ({
    id: r.id as number,
    season_id: r.season_id as number | null,
    league_id: r.league_id as number,
    venue_id: r.venue_id as number | null,
    home_team_id: r.home_team_id as number,
    away_team_id: r.away_team_id as number,
    starting_at: r.starting_at as string,
    state: r.state as string | null,
    round: r.round as string | null,
    matchday: r.matchday as number | null,
    home_score: r.home_score as number | null,
    away_score: r.away_score as number | null,
    home_ht_score: r.home_ht_score as number | null,
    away_ht_score: r.away_ht_score as number | null,
    attendance: r.attendance as number | null,
    home_team_name: r.home_team_name as string,
    home_team_short: r.home_team_short as string | null,
    home_team_logo: r.home_team_logo as string | null,
    home_team_primary_color: r.home_team_primary_color as string | null,
    home_team_secondary_color: r.home_team_secondary_color as string | null,
    away_team_name: r.away_team_name as string,
    away_team_short: r.away_team_short as string | null,
    away_team_logo: r.away_team_logo as string | null,
    away_team_primary_color: r.away_team_primary_color as string | null,
    away_team_secondary_color: r.away_team_secondary_color as string | null,
    venue_name: r.venue_name as string | null,
    venue_city: r.venue_city as string | null,
    prediction: mapPrediction(r),
  }));
}

/**
 * Devuelve la jornada FUTURA que arranca antes (la más próxima a abrir).
 * Si todas las futuras ya empezaron, devuelve la primera del listado.
 */
export function getNextOpenJornada(): JornadaOption | null {
  const all = getUpcomingJornadas(180);
  if (all.length === 0) return null;
  // 1ra que NO haya empezado
  const next = all.find((j) => !j.has_started);
  return next ?? all[0];
}
