// Tipos compartidos — mapeo manual del schema de la BD.
// Mantener sincronizado con `data/predictions_mx.db` schema.

export interface Team {
  id: number;
  name: string;
  short_code: string | null;
  country: string | null;
  founded: number | null;
  venue_id: number | null;
  logo_url: string | null;
  primary_color: string | null;
  secondary_color: string | null;
}

export interface Venue {
  id: number;
  name: string;
  city: string | null;
  state: string | null;
  country: string | null;
  altitude_m: number | null;
  latitude: number | null;
  longitude: number | null;
  capacity: number | null;
  surface: string | null;
  roof_type: string | null;
  climate_zone: string | null;
}

export interface Season {
  id: number;
  league_id: number;
  name: string;
  start_date: string | null;
  end_date: string | null;
  is_current: number | null;
}

export interface Fixture {
  id: number;
  season_id: number | null;
  league_id: number;
  venue_id: number | null;
  home_team_id: number;
  away_team_id: number;
  starting_at: string;
  state: string | null;
  round: string | null;
  matchday: number | null;
  home_score: number | null;
  away_score: number | null;
  home_ht_score: number | null;
  away_ht_score: number | null;
  attendance: number | null;
}

export interface FixtureWithTeams extends Fixture {
  home_team_name: string;
  home_team_short: string | null;
  home_team_logo: string | null;
  home_team_primary_color: string | null;
  home_team_secondary_color: string | null;
  away_team_name: string;
  away_team_short: string | null;
  away_team_logo: string | null;
  away_team_primary_color: string | null;
  away_team_secondary_color: string | null;
  venue_name: string | null;
  venue_city: string | null;
}

export interface FixtureDetail extends FixtureWithTeams {
  venue_altitude_m?: number | null;
  venue_capacity?: number | null;
  season_name?: string | null;
}

export interface TeamFixture extends FixtureWithTeams {
  is_home: 0 | 1;
}

export interface AnalystPrediction {
  id: number;
  fixture_id: number;
  home_win: number | null;       // 0..1
  draw: number | null;           // 0..1
  away_win: number | null;       // 0..1
  confidence: number | null;
  predicted_home_goals: number | null;
  predicted_away_goals: number | null;
  most_likely_score: string | null;
  key_factors: string | null;
  contrarian_view: string | null;
  derby_flag: number | null;
  derby_name: string | null;
  created_at: string | null;
  is_backtest?: number | null;
}

/**
 * Shape "card-ready" que la UI consume: incluye aliases (home_win_prob etc.)
 * y el outcome derivado (home_win/draw/away_win) calculado desde el score.
 */
export interface PredictionView extends AnalystPrediction {
  predicted_outcome: string | null;
  home_win_prob: number | null;
  draw_prob: number | null;
  away_win_prob: number | null;
}

export interface FixtureWithPrediction extends FixtureWithTeams {
  prediction: PredictionView | null;
}

export type Outcome = 'home_win' | 'away_win' | 'draw';

export interface HistoryRow {
  id: number;
  fixture_id: number;
  starting_at: string;
  home_team_name: string;
  home_team_short: string | null;
  away_team_name: string;
  away_team_short: string | null;
  home_score: number | null;
  away_score: number | null;
  home_win: number | null;
  draw: number | null;
  away_win: number | null;
  predicted_outcome: Outcome | null;
  confidence: number | null;
  most_likely_score: string | null;
  predicted_at: string | null;
  matchday: number | null;
  season_id: number | null;
  matchday_ordinal: number | null;
  is_backtest: boolean;
  // Derivados:
  status: 'pending' | 'finished' | 'live';
  pick_correct: boolean | null;
  implicit_outcome: Outcome | null;
  probs_outcome: Outcome | null;
  has_conflict: boolean;
}

export interface HistoryStats {
  total: number;
  finished: number;
  pending: number;
  hits: number;
  misses: number;
  accuracy: number | null;
  brier: number | null;
  by_outcome: Record<string, { total: number; hits: number; accuracy: number | null }>;
  current_streak: { type: 'W' | 'L' | null; length: number };
  last_5: ('W' | 'L' | null)[];
}

// ─── Outcome derivations (lógica de pick) ────────────────────────────────

/**
 * Fuente de verdad para el pick: el score esperado (most_likely_score).
 * "X-Y" con X > Y → Local · X < Y → Visita · X = Y → Empate.
 * Las probs 1X2 son info adicional y pueden contradecir el score.
 */
export function deriveOutcome(
  h: number | null,
  d: number | null,
  a: number | null,
  mostLikelyScore: string | null,
): Outcome | null {
  if (mostLikelyScore) {
    const m = mostLikelyScore.match(/^(\d+)-(\d+)$/);
    if (m) {
      const hg = parseInt(m[1], 10);
      const ag = parseInt(m[2], 10);
      if (hg > ag) return 'home_win';
      if (hg < ag) return 'away_win';
      return 'draw';
    }
  }
  if (h === null || d === null || a === null) return null;
  const maxProb = Math.max(h, d, a);
  if (maxProb < 0.40) return null;
  if (h >= d && h >= a) return 'home_win';
  if (a >= d && a >= h) return 'away_win';
  return 'draw';
}

/** Outcome derivado del max_prob 1X2. Usado para detectar conflicto score↔probs. */
export function deriveOutcomeFromProbs(
  h: number | null,
  d: number | null,
  a: number | null,
): Outcome | null {
  if (h === null || d === null || a === null) return null;
  if (h >= d && h >= a) return 'home_win';
  if (a >= d && a >= h) return 'away_win';
  return 'draw';
}
