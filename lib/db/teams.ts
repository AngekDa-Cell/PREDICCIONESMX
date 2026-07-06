// Queries de equipos

import { db } from "./client";
import type { Team, TeamFixture } from "./types";

/**
 * Lista plana de equipos activos en Liga MX.
 * Excluye equipos que no aparecen en fixtures de league_id=743.
 */
export function getAllTeams(): Team[] {
  const stmt = db.prepare(`
    SELECT DISTINCT
      t.id, t.name, t.short_code, t.country, t.founded,
      t.venue_id, t.logo_url, t.primary_color, t.secondary_color
    FROM teams t
    WHERE t.id IN (
      SELECT DISTINCT home_team_id FROM fixtures WHERE league_id = 743
      UNION
      SELECT DISTINCT away_team_id FROM fixtures WHERE league_id = 743
    )
    ORDER BY t.name ASC
  `);
  return stmt.all() as Team[];
}

/**
 * Detalle de un equipo por ID.
 */
export function getTeamById(id: number): Team | null {
  const stmt = db.prepare(`SELECT * FROM teams WHERE id = ?`);
  return stmt.get(id) as Team | null;
}

/**
 * Partidos recientes de un equipo (últimos N terminados).
 */
export function getTeamRecentFixtures(
  teamId: number,
  limit = 10,
): TeamFixture[] {
  const stmt = db.prepare(`
    SELECT
      ${FIXTURE_COLS},
      CASE WHEN f.home_team_id = ? THEN 1 ELSE 0 END AS is_home
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    WHERE f.league_id = 743
      AND (f.home_team_id = ? OR f.away_team_id = ?)
      AND f.home_score IS NOT NULL
    ORDER BY f.starting_at DESC
    LIMIT ?
  `);
  return stmt.all(teamId, teamId, teamId, limit) as TeamFixture[];
}

/**
 * Próximos partidos de un equipo.
 */
export function getTeamUpcomingFixtures(
  teamId: number,
  limit = 5,
): TeamFixture[] {
  const stmt = db.prepare(`
    SELECT
      ${FIXTURE_COLS},
      CASE WHEN f.home_team_id = ? THEN 1 ELSE 0 END AS is_home
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    LEFT JOIN venues v ON v.id = f.venue_id
    WHERE f.league_id = 743
      AND (f.home_team_id = ? OR f.away_team_id = ?)
      AND f.home_score IS NULL
      AND f.starting_at >= datetime('now')
    ORDER BY f.starting_at ASC
    LIMIT ?
  `);
  return stmt.all(teamId, teamId, teamId, limit) as TeamFixture[];
}

const FIXTURE_COLS = `
  f.id, f.season_id, f.league_id, f.venue_id,
  f.home_team_id, f.away_team_id, f.starting_at, f.state, f.round, f.matchday,
  f.home_score, f.away_score, f.home_ht_score, f.away_ht_score, f.attendance,
  ht.name AS home_team_name, ht.short_code AS home_team_short,
  at.name AS away_team_name, at.short_code AS away_team_short,
  v.name AS venue_name, v.city AS venue_city
`;
