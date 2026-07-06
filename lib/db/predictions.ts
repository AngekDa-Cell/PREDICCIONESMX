// Queries de predicciones y historial

import { db } from "./client";
import { getMatchdayOrdinalByDate } from "./matchday";
import {
  deriveOutcome,
  deriveOutcomeFromProbs,
  type PredictionView,
  type AnalystPrediction,
  type HistoryRow,
  type Outcome,
} from "./types";

/**
 * Última predicción para un fixture (con outcome derivado).
 */
export function getLatestPredictionForFixture(
  fixtureId: number,
): AnalystPrediction | null {
  const stmt = db.prepare(`
    SELECT * FROM analyst_predictions
    WHERE fixture_id = ?
    ORDER BY created_at DESC
    LIMIT 1
  `);
  return stmt.get(fixtureId) as AnalystPrediction | null;
}

export function getPredictionView(
  fixtureId: number,
): PredictionView | null {
  const row = getLatestPredictionForFixture(fixtureId);
  if (!row) return null;
  return {
    ...row,
    predicted_outcome: deriveOutcome(
      row.home_win,
      row.draw,
      row.away_win,
      row.most_likely_score,
    ),
    home_win_prob: row.home_win,
    draw_prob: row.draw,
    away_win_prob: row.away_win,
  };
}

// ─── Historial ──────────────────────────────────────────────────────────

export function getPredictionHistory(): HistoryRow[] {
  const stmt = db.prepare(`
    SELECT
      f.id, f.season_id, f.matchday, f.starting_at,
      f.home_score, f.away_score,
      ht.name AS home_team_name, ht.short_code AS home_team_short,
      at.name AS away_team_name, at.short_code AS away_team_short,
      p.fixture_id AS p_fixture_id,
      p.home_win AS p_home_win, p.draw AS p_draw, p.away_win AS p_away_win,
      p.confidence AS p_confidence,
      p.most_likely_score AS p_most_likely_score,
      p.created_at AS p_created_at,
      p.is_backtest AS p_is_backtest,
      p.predicted_home_goals AS p_predicted_home_goals,
      p.predicted_away_goals AS p_predicted_away_goals
    FROM fixtures f
    JOIN teams ht ON ht.id = f.home_team_id
    JOIN teams at ON at.id = f.away_team_id
    JOIN (
      SELECT ap1.* FROM analyst_predictions ap1
      INNER JOIN (
        SELECT fixture_id, MAX(created_at) AS max_created
        FROM analyst_predictions GROUP BY fixture_id
      ) ap2 ON ap1.fixture_id = ap2.fixture_id AND ap1.created_at = ap2.max_created
    ) p ON p.fixture_id = f.id
    WHERE f.league_id = 743
    ORDER BY f.starting_at DESC
  `);
  const rows = stmt.all() as Record<string, unknown>[];

  return rows.map((r) => {
    const outcome = deriveOutcome(
      r.p_home_win as number | null,
      r.p_draw as number | null,
      r.p_away_win as number | null,
      r.p_most_likely_score as string | null,
    );
    const probsOutcome = deriveOutcomeFromProbs(
      r.p_home_win as number | null,
      r.p_draw as number | null,
      r.p_away_win as number | null,
    );
    const hasConflict =
      outcome !== null &&
      probsOutcome !== null &&
      outcome !== probsOutcome;

    let status: 'pending' | 'finished' | 'live' = 'pending';
    let pickCorrect: boolean | null = null;

    if (r.home_score !== null && r.away_score !== null) {
      status = 'finished';
      const real =
        (r.home_score as number) > (r.away_score as number)
          ? 'home_win'
          : (r.home_score as number) < (r.away_score as number)
          ? 'away_win'
          : 'draw';
      pickCorrect = outcome === null ? null : outcome === real;
    } else {
      const now = new Date();
      const start = new Date(r.starting_at as string);
      const startedHours = (now.getTime() - start.getTime()) / 3_600_000;
      if (startedHours > -2 && startedHours < 4) status = 'live';
    }

    const implicitOutcome = (() => {
      const hg = r.p_predicted_home_goals as number | null;
      const ag = r.p_predicted_away_goals as number | null;
      if (hg !== null && ag !== null) {
        if (hg > ag) return 'home_win';
        if (hg < ag) return 'away_win';
        return 'draw';
      }
      return null;
    })() as Outcome | null;

    return {
      id: r.id as number,
      fixture_id: r.id as number,
      starting_at: r.starting_at as string,
      home_team_name: r.home_team_name as string,
      home_team_short: r.home_team_short as string | null,
      away_team_name: r.away_team_name as string,
      away_team_short: r.away_team_short as string | null,
      home_score: r.home_score as number | null,
      away_score: r.away_score as number | null,
      home_win: r.p_home_win as number | null,
      draw: r.p_draw as number | null,
      away_win: r.p_away_win as number | null,
      predicted_outcome: outcome,
      implicit_outcome: implicitOutcome,
      probs_outcome: probsOutcome,
      has_conflict: hasConflict,
      confidence: r.p_confidence as number | null,
      most_likely_score: r.p_most_likely_score as string | null,
      predicted_at: r.p_created_at as string | null,
      matchday: r.matchday as number | null,
      season_id: r.season_id as number | null,
      matchday_ordinal: getMatchdayOrdinalByDate(
        r.season_id as number | null,
        r.matchday as number | null,
        r.starting_at as string | null,
      ),
      is_backtest: (r.p_is_backtest ?? 0) === 1,
      status,
      pick_correct: pickCorrect,
    };
  });
}
