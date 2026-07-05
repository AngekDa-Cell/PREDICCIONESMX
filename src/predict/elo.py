"""
elo.py — Implementación de Elo Rating dinámico para Liga MX.

Inspirado en FiveThirtyEight (Nate Silver) y metodologías académicas.
- Rating inicial: 1500
- K-factor: 20 (estándar), ajustado por goal difference
- Home advantage: ~100 puntos Elo (≈ 60% win rate)
- Update incremental después de cada partido

Paper clave: "Glickman & Hennessy (2014) — A stochastic rank-based model"
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, List


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

ELO_BASE = 1500.0
ELO_K_FACTOR = 20.0
HOME_ADVANTAGE_ELO = 100.0  # ≈ 60% win rate para local
MAX_K_BIG_WIN = 1.5  # boost K para victorias abultadas (Glickman)

# ─────────────────────────────────────────────────────────────────────────────
# SHRINKAGE (Fase 6)
# ─────────────────────────────────────────────────────────────────────────────
# Factor de contracción del Elo hacia el promedio (1500).
# Problema: el Elo Liga MX está sistemáticamente sobreestimado vs win rate real
# (drift promedio +25% en backtest).
# Solución: shrinkage = 0.7 reduce cada rating hacia 1500 por un factor 0.7.
# Calibrado con grid search sobre backtest 2025 (340 partidos):
#   shrinkage=1.0 → acc 55.29%, brier 0.5996 (baseline)
#   shrinkage=0.7 → acc 55.59%, brier 0.5858 (óptimo: mejor balance)
#   shrinkage=0.5 → acc 53.24%, brier 0.5873 (demasiada contracción)
DEFAULT_SHRINKAGE_FACTOR = 0.7


def apply_shrinkage(elo: float, factor: float, anchor: float = ELO_BASE) -> float:
    """
    Aplica shrinkage al Elo: contrae hacia anchor (default 1500).

    Args:
        elo: Elo rating actual
        factor: factor de shrinkage [0, 1]
            1.0 = sin cambios
            0.7 = default (reduce 30% hacia anchor)
            0.0 = todos en anchor
        anchor: rating objetivo (default 1500)

    Returns:
        Elo ajustado
    """
    return anchor + (elo - anchor) * factor


def expected_score(rating_a: float, rating_b: float, home_advantage: float = 0) -> float:
    """Elo expected score formula: E = 1 / (1 + 10^((Rb - Ra - HA)/400))."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a - home_advantage) / 400.0))


def k_multiplier(goal_diff: int) -> float:
    """
    K-factor multiplier según goal difference (5ThirtyEight).
    Ganaste por mucho → K mayor (mayor cambio de rating).
    """
    if goal_diff <= 0:
        return 1.0
    # log-based: +0.5 por cada gol de diferencia
    import math
    return 1.0 + 0.5 * math.log2(1 + goal_diff)


def actual_score(home_score: int, away_score: int) -> tuple:
    """
    Retorna (actual_home, actual_away) en formato Elo.
    - Victoria local: (1, 0)
    - Empate: (0.5, 0.5)
    - Derrota local: (0, 1)
    """
    if home_score > away_score:
        return 1.0, 0.0
    elif home_score < away_score:
        return 0.0, 1.0
    else:
        return 0.5, 0.5


# ─────────────────────────────────────────────────────────────────────────────
# ELO STATE
# ─────────────────────────────────────────────────────────────────────────────

class EloState:
    """Mantiene el estado de Elo para todos los equipos."""
    def __init__(self):
        self.ratings: Dict[int, float] = {}  # team_id → rating

    def get(self, team_id: int) -> float:
        return self.ratings.get(team_id, ELO_BASE)

    def update_match(self, home_id: int, away_id: int, home_score: int, away_score: int):
        """Actualiza ratings después de un partido."""
        rh = self.get(home_id)
        ra = self.get(away_id)

        eh = expected_score(rh, ra, HOME_ADVANTAGE_ELO)
        ea = 1 - eh

        sh, sa = actual_score(home_score, away_score)

        goal_diff = abs(home_score - away_score)
        km = k_multiplier(goal_diff)

        new_rh = rh + ELO_K_FACTOR * km * (sh - eh)
        new_ra = ra + ELO_K_FACTOR * km * (sa - ea)

        self.ratings[home_id] = new_rh
        self.ratings[away_id] = new_ra

    def update_all(self, conn: sqlite3.Connection, league_id: int = 743):
        """
        Construye todos los ratings desde el inicio de los datos disponibles.
        Procesa partidos cronológicamente.
        """
        rows = conn.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score, starting_at
            FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
            ORDER BY starting_at
        """, (league_id,)).fetchall()

        for home_id, away_id, hs, as_, _ in rows:
            self.update_match(home_id, away_id, hs, as_)

        return self


def predict_1x2_elo(
    home_elo: float,
    away_elo: float,
    home_advantage: float = HOME_ADVANTAGE_ELO,
    shrinkage_factor: float = DEFAULT_SHRINKAGE_FACTOR,
    home_team_shrink: float = 1.0,
    away_team_shrink: float = 1.0,
) -> Dict[str, float]:
    """
    Predice P(home), P(draw), P(away) usando distribución de probabilidad
    basada en la diferencia de Elo.

    Usa aproximación normal con sigma=140 (estándar para distribución de goals).

    Args:
        home_elo: Elo del equipo local (pre-shrinkage)
        away_elo: Elo del equipo visitante (pre-shrinkage)
        home_advantage: ventaja de local en puntos Elo
        shrinkage_factor: factor de contracción GLOBAL hacia 1500 [0, 1]
            1.0 = sin shrinkage, 0.7 = default (óptimo), 0.0 = todos en 1500
        home_team_shrink: factor de shrinkage ESPECÍFICO del equipo local (como local)
        away_team_shrink: factor de shrinkage ESPECÍFICO del equipo visitante (como visitante)

    El shrinkage final es el producto: shrinkage * team_shrink.
    """
    # Aplicar shrinkage global
    if shrinkage_factor != 1.0:
        home_elo = ELO_BASE + (home_elo - ELO_BASE) * shrinkage_factor
        away_elo = ELO_BASE + (away_elo - ELO_BASE) * shrinkage_factor

    # Aplicar shrinkage específico del equipo
    if home_team_shrink != 1.0:
        home_elo = ELO_BASE + (home_elo - ELO_BASE) * home_team_shrink
    if away_team_shrink != 1.0:
        away_elo = ELO_BASE + (away_elo - ELO_BASE) * away_team_shrink

    # Diferencia de Elo con home advantage
    elo_diff = home_elo - away_elo + home_advantage

    # Probabilidad de victoria basada en diferencia
    p_home_raw = expected_score(home_elo, away_elo, home_advantage)

    # Distribución de goals (Poisson bivariado simplificado)
    # Asumimos goles promedio = 1.3 home, 1.0 away
    avg_home = 1.3
    avg_away = 1.0

    # Calculamos expected goals ajustados por Elo
    # Cada 100 puntos Elo de diferencia = +0.3 goles esperados
    goal_adj = elo_diff / 100 * 0.3

    exp_home_goals = max(0.5, avg_home + goal_adj / 2)
    exp_away_goals = max(0.5, avg_away - goal_adj / 2)

    # Probabilidades usando Poisson
    import math
    def poisson_pmf(k, lam):
        return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))

    home_win = draw = away_win = 0.0
    for h in range(11):
        for a in range(11):
            p = poisson_pmf(h, exp_home_goals) * poisson_pmf(a, exp_away_goals)
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

    # Normalizar
    total = home_win + draw + away_win
    if total > 0:
        home_win /= total; draw /= total; away_win /= total

    return {
        'home_win': round(home_win, 4),
        'draw': round(draw, 4),
        'away_win': round(away_win, 4),
        'elo_diff': round(elo_diff, 1),
        'home_elo': round(home_elo, 1),
        'away_elo': round(away_elo, 1),
        'expected_home_goals': round(exp_home_goals, 2),
        'expected_away_goals': round(exp_away_goals, 2),
        'p_home_raw': round(p_home_raw, 4),  # sin draw split
    }


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_elo_predictions(
    conn: sqlite3.Connection,
    home_team_id: int,
    away_team_id: int,
    before_date: Optional[str] = None,
    league_id: int = 743,
    shrinkage_factor: float = DEFAULT_SHRINKAGE_FACTOR,
    team_shrinkages: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Calcula el Elo de los equipos hasta before_date, luego predice el partido.

    Args:
        shrinkage_factor: factor de contracción global hacia 1500 (default 0.7).
        team_shrinkages: dict opcional con shrinkage por equipo y localía:
            {team_name: {"shrinkage_local": 0.8, "shrinkage_visit": 0.6, ...}}
            Si es None, intenta cargar desde data/team_local_shrinkage.json
    """
    if before_date:
        rows = conn.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
              AND starting_at < ?
            ORDER BY starting_at
        """, (league_id, before_date)).fetchall()
    else:
        rows = conn.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
              AND (starting_at < (SELECT MIN(starting_at) FROM fixtures WHERE league_id = ? AND starting_at > ?))
            ORDER BY starting_at
        """, (league_id, league_id, before_date or '9999-12-31')).fetchall()

    state = EloState()
    for home_id, away_id, hs, as_ in rows:
        state.update_match(home_id, away_id, hs, as_)

    home_elo = state.get(home_team_id)
    away_elo = state.get(away_team_id)

    # Guardar Elo raw antes de shrinkage
    home_elo_raw = home_elo
    away_elo_raw = away_elo

    # Cargar shrinkage por equipo si está disponible
    if team_shrinkages is None:
        team_shrinkages = _load_team_shrinkages()

    home_name = conn.execute("SELECT name FROM teams WHERE id = ?", (home_team_id,)).fetchone()
    away_name = conn.execute("SELECT name FROM teams WHERE id = ?", (away_team_id,)).fetchone()
    # fetchone() devuelve tupla, no dict. Usar [0] en lugar de ['name'].
    home_team_shrink = team_shrinkages.get(home_name[0] if home_name else "", {}).get("shrinkage_local", 1.0)
    away_team_shrink = team_shrinkages.get(away_name[0] if away_name else "", {}).get("shrinkage_visit", 1.0)

    prediction = predict_1x2_elo(
        home_elo, away_elo,
        shrinkage_factor=shrinkage_factor,
        home_team_shrink=home_team_shrink,
        away_team_shrink=away_team_shrink,
    )

    # Reemplazar los Elo reportados con los valores post-shrinkage (combinado)
    effective_shrink_home = shrinkage_factor * home_team_shrink
    effective_shrink_away = shrinkage_factor * away_team_shrink
    prediction['home_elo'] = round(ELO_BASE + (home_elo_raw - ELO_BASE) * effective_shrink_home, 1)
    prediction['away_elo'] = round(ELO_BASE + (away_elo_raw - ELO_BASE) * effective_shrink_away, 1)
    prediction['elo_raw_home'] = round(home_elo_raw, 1)
    prediction['elo_raw_away'] = round(away_elo_raw, 1)
    prediction['shrinkage_factor'] = shrinkage_factor
    prediction['home_team_shrink'] = home_team_shrink
    prediction['away_team_shrink'] = away_team_shrink

    return {
        **prediction,
        'home_team_id': home_team_id,
        'away_team_id': away_team_id,
        'before_date': before_date,
        'games_processed': len(rows),
    }


def _load_team_shrinkages() -> Dict[str, Dict[str, Any]]:
    """Carga shrinkage por equipo desde data/team_local_shrinkage.json."""
    import json
    path = Path(__file__).parent.parent.parent / "data" / "team_local_shrinkage.json"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("teams", {})
    except (json.JSONDecodeError, IOError):
        return {}


def get_team_elo_rating(
    conn: sqlite3.Connection,
    team_id: int,
    before_date: Optional[str] = None,
    league_id: int = 743
) -> Dict[str, Any]:
    """Retorna el Elo rating actual de un equipo + info."""
    if before_date:
        rows = conn.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
              AND starting_at < ?
              AND (home_team_id = ? OR away_team_id = ?)
            ORDER BY starting_at DESC
            LIMIT 20
        """, (league_id, before_date, team_id, team_id)).fetchall()
    else:
        rows = conn.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
              AND (home_team_id = ? OR away_team_id = ?)
            ORDER BY starting_at DESC
            LIMIT 20
        """, (league_id, team_id, team_id)).fetchall()

    # Construir historial completo para llegar al Elo actual
    all_rows = conn.execute("""
        SELECT home_team_id, away_team_id, home_score, away_score
        FROM fixtures
        WHERE league_id = ?
          AND home_score IS NOT NULL
          AND starting_at < ?
        ORDER BY starting_at
    """, (league_id, before_date or '9999-12-31')).fetchall() if before_date else conn.execute("""
        SELECT home_team_id, away_team_id, home_score, away_score
        FROM fixtures
        WHERE league_id = ?
          AND home_score IS NOT NULL
        ORDER BY starting_at
    """, (league_id,)).fetchall()

    state = EloState()
    for home_id, away_id, hs, as_ in all_rows:
        state.update_match(home_id, away_id, hs, as_)

    rating = state.get(team_id)

    # Calcular tendencia (últimos 5 partidos)
    trend = []
    for home_id, away_id, hs, as_ in rows[:5]:
        if home_id == team_id:
            trend.append('W' if hs > as_ else 'D' if hs == as_ else 'L')
        else:
            trend.append('W' if as_ > hs else 'D' if as_ == hs else 'L')

    return {
        'team_id': team_id,
        'elo_rating': round(rating, 1),
        'deviation_from_baseline': round(rating - ELO_BASE, 1),
        'last_5_form': '-'.join(reversed(trend)) if trend else '',
        'is_above_average': rating > ELO_BASE,
    }


def get_elo_rankings(
    conn: sqlite3.Connection,
    before_date: Optional[str] = None,
    league_id: int = 743
) -> List[Dict[str, Any]]:
    """Lista todos los equipos ordenados por Elo."""
    if before_date:
        rows = conn.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
              AND starting_at < ?
            ORDER BY starting_at
        """, (league_id, before_date)).fetchall()
    else:
        rows = conn.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
            ORDER BY starting_at
        """, (league_id,)).fetchall()

    state = EloState()
    for home_id, away_id, hs, as_ in rows:
        state.update_match(home_id, away_id, hs, as_)

    # Obtener nombres de equipos
    team_names = {}
    for tid, name in conn.execute("SELECT id, name FROM teams").fetchall():
        team_names[tid] = name

    rankings = []
    for team_id, rating in sorted(state.ratings.items(), key=lambda x: -x[1]):
        rankings.append({
            'team_id': team_id,
            'name': team_names.get(team_id, f'Team {team_id}'),
            'elo_rating': round(rating, 1),
        })

    return rankings
