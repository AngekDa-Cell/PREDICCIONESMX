// Queries de stats agregadas

import { db } from "./client";
import type { HistoryStats, HistoryRow, Outcome } from "./types";

// ─── Fixture counts ───────────────────────────────────────────────────────

export function getFixtureCounts(): { upcoming: number; finished: number } {
  const up = db
    .prepare(
      `SELECT COUNT(*) as n FROM fixtures
       WHERE league_id = 743 AND home_score IS NULL
         AND starting_at >= datetime('now')
         AND starting_at <= datetime('now', '+30 days')`,
    )
    .get() as { n: number };
  const fin = db
    .prepare(
      `SELECT COUNT(*) as n FROM fixtures
       WHERE league_id = 743 AND home_score IS NOT NULL
         AND starting_at < datetime('now')`,
    )
    .get() as { n: number };
  return { upcoming: up.n, finished: fin.n };
}

// ─── History stats ───────────────────────────────────────────────────────

function brierOne(
  p_h: number | null,
  p_d: number | null,
  p_a: number | null,
  real: Outcome,
): number {
  const ph = p_h ?? 0.33;
  const pd = p_d ?? 0.33;
  const pa = p_a ?? 0.33;
  const rh = real === 'home_win' ? 1 : 0;
  const rd = real === 'draw' ? 1 : 0;
  const ra = real === 'away_win' ? 1 : 0;
  return (ph - rh) ** 2 + (pd - rd) ** 2 + (pa - ra) ** 2;
}

export function getHistoryStats(history: HistoryRow[]): HistoryStats {
  // SOLO predicciones LIVE (no backtest) cuentan para accuracy/racha
  const live = history.filter((h) => !h.is_backtest);
  const finished = live.filter((h) => h.status === 'finished');
  const pending = live.filter((h) => h.status !== 'finished');
  const hits = finished.filter((h) => h.pick_correct === true).length;
  const misses = finished.filter((h) => h.pick_correct === false).length;
  const accuracy = finished.length > 0 ? hits / finished.length : null;

  // Brier promedio
  let brierSum = 0;
  let brierCount = 0;
  for (const h of finished) {
    if (h.home_score === null || h.away_score === null) continue;
    const real: Outcome =
      h.home_score > h.away_score
        ? 'home_win'
        : h.home_score < h.away_score
        ? 'away_win'
        : 'draw';
    brierSum += brierOne(h.home_win, h.draw, h.away_win, real);
    brierCount++;
  }
  const brier = brierCount > 0 ? brierSum / brierCount : null;

  // Por outcome
  const byOutcome: HistoryStats['by_outcome'] = {
    home_win: { total: 0, hits: 0, accuracy: null },
    draw: { total: 0, hits: 0, accuracy: null },
    away_win: { total: 0, hits: 0, accuracy: null },
  };
  for (const h of finished) {
    if (!h.predicted_outcome) continue;
    const oc = byOutcome[h.predicted_outcome];
    if (!oc) continue;
    oc.total++;
    if (h.pick_correct) oc.hits++;
  }
  for (const k of Object.keys(byOutcome)) {
    const o = byOutcome[k];
    o.accuracy = o.total > 0 ? o.hits / o.total : null;
  }

  // Racha actual y últimos 5
  const chronological = [...finished].sort(
    (a, b) =>
      new Date(b.starting_at).getTime() - new Date(a.starting_at).getTime(),
  );
  const last5 = chronological.slice(0, 5).map((h) =>
    h.pick_correct === true ? 'W' : h.pick_correct === false ? 'L' : null,
  );
  let streakType: 'W' | 'L' | null = null;
  let streakLen = 0;
  for (const h of chronological) {
    const t =
      h.pick_correct === true ? 'W' : h.pick_correct === false ? 'L' : null;
    if (t === null) break;
    if (streakType === null) {
      streakType = t;
      streakLen = 1;
    } else if (t === streakType) {
      streakLen++;
    } else {
      break;
    }
  }

  return {
    total: live.length,
    finished: finished.length,
    pending: pending.length,
    hits,
    misses,
    accuracy,
    brier,
    by_outcome: byOutcome,
    current_streak: { type: streakType, length: streakLen },
    last_5: last5,
  };
}
