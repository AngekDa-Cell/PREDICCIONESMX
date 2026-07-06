// Matchday ordinal mapping
//
// SportMonks devuelve matchday como ID interno (ej. 407241),
// no como ordinal humano ("Jornada 1").
// Mapeamos: season_id+matchday → ordinal 1, 2, 3, ...
// Para partidos sin matchday, agrupamos por DATE(starting_at).

import { db } from "./client";

function buildMatchdayOrdinalMap(): Map<string, number> {
  // 1. Partidos CON matchday poblada
  const withMatchday = db.prepare(`
    SELECT season_id, matchday, MIN(starting_at) AS first_date
    FROM fixtures
    WHERE league_id = 743 AND matchday IS NOT NULL
    GROUP BY season_id, matchday
    ORDER BY season_id DESC, first_date ASC
  `).all() as { season_id: number; matchday: number; first_date: string }[];

  // 2. Partidos SIN matchday (viejos): agrupar por DATE(starting_at)
  const byDate = db.prepare(`
    SELECT season_id, DATE(starting_at) AS day, MIN(starting_at) AS first_date
    FROM fixtures
    WHERE league_id = 743 AND matchday IS NULL
    GROUP BY season_id, DATE(starting_at)
    ORDER BY season_id DESC, first_date ASC
  `).all() as { season_id: number; day: string; first_date: string }[];

  const perSeason: Record<number, number> = {};
  const map = new Map<string, number>();

  const allBySeason: Record<number, Array<{ key: string; first_date: string }>> = {};
  for (const r of withMatchday) {
    (allBySeason[r.season_id] ??= []).push({
      key: `m:${r.matchday}`,
      first_date: r.first_date,
    });
  }
  for (const r of byDate) {
    (allBySeason[r.season_id] ??= []).push({
      key: `d:${r.day}`,
      first_date: r.first_date,
    });
  }

  for (const seasonId of Object.keys(allBySeason)) {
    const items = allBySeason[Number(seasonId)].sort((a, b) =>
      a.first_date.localeCompare(b.first_date),
    );
    for (const item of items) {
      perSeason[Number(seasonId)] = (perSeason[Number(seasonId)] ?? 0) + 1;
      map.set(`${seasonId}:${item.key}`, perSeason[Number(seasonId)]);
    }
  }

  return map;
}

let matchdayOrdinalMap: Map<string, number> | null = null;

function ensureMap(): Map<string, number> {
  if (!matchdayOrdinalMap) matchdayOrdinalMap = buildMatchdayOrdinalMap();
  return matchdayOrdinalMap;
}

/** Devuelve el ordinal humano (1, 2, 3...) para un (season_id, matchday). */
export function getMatchdayOrdinal(
  seasonId: number | null,
  matchday: number | null,
): number | null {
  if (seasonId === null) return null;
  const map = ensureMap();
  if (matchday !== null) {
    const m = map.get(`${seasonId}:m:${matchday}`);
    if (m !== undefined) return m;
  }
  return null;
}

/** Devuelve el ordinal humano (1, 2, 3...) usando también la fecha como fallback. */
export function getMatchdayOrdinalByDate(
  seasonId: number | null,
  matchday: number | null,
  date: string | null,
): number | null {
  if (seasonId === null) return null;
  const map = ensureMap();
  if (matchday !== null) {
    const m = map.get(`${seasonId}:m:${matchday}`);
    if (m !== undefined) return m;
  }
  if (date) {
    const day = date.slice(0, 10);
    const d = map.get(`${seasonId}:d:${day}`);
    if (d !== undefined) return d;
  }
  return null;
}

/** Versión "Jornada N" o null. */
export function getMatchdayLabel(
  seasonId: number | null,
  matchday: number | null,
): string | null {
  const ord = getMatchdayOrdinal(seasonId, matchday);
  return ord !== null ? `Jornada ${ord}` : null;
}
