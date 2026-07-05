"""
dixon_coles.py — Dixon-Coles Poisson Model para predicción de goles.

Implementación del modelo de Mark Dixon & Stuart Coles (1997):
- Goles de local y visitante modelados como Poisson independientes
- Corrección τ(μ) para subestimación de scorelines 0-0 y 1-1
- Parámetros: attack[team], defense[team], home_advantage
- Fitting por maximum likelihood
- Time-decay weighting (partidos recientes pesan más)

Referencia: "Modelling Association Football Scores and Inefficiencies in the
             Football Betting Market" — Dixon & Coles, 1997
"""

import math
import sqlite3
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import json


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TeamParams:
    team_id: int
    name: str
    attack: float       # > 1 = ataque mejor que promedio
    defense: float      # > 1 = defensa peor que promedio (goals conceded)
    home_adv: float     # ventaja local adicional


@dataclass
class DCModel:
    home_params: Dict[int, float]   # team_id → param
    away_params: Dict[int, float]
    global_attack: float             # ataque promedio (baseline = 1.0)
    home_advantage: float            # α (factor local global)
    rho: float                       # τ correlación para low scores
    league_avg_goals: float


# ─────────────────────────────────────────────────────────────────────────────
# POISSON PMF
# ─────────────────────────────────────────────────────────────────────────────

def poisson_pmf(k: int, lam: float) -> float:
    """P(X=k) para Poisson(λ)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    # log-space para estabilidad numérica
    return math.exp(k * math.log(lam) - lam - _log_factorial(k))


_log_factorial_cache = {0: 0.0, 1: 0.0}
def _log_factorial(n: int) -> float:
    """Stirling aprox para n! en log-space."""
    if n in _log_factorial_cache:
        return _log_factorial_cache[n]
    # Exact para n <= 20, luego Stirling
    if n <= 20:
        val = sum(math.log(i) for i in range(1, n + 1))
    else:
        val = n * math.log(n) - n + 0.5 * math.log(2 * math.pi * n)
    _log_factorial_cache[n] = val
    return val


def poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) para Poisson(λ)."""
    return sum(poisson_pmf(i, lam) for i in range(k + 1))


# ─────────────────────────────────────────────────────────────────────────────
# DIXON-COLES PROBABILITY (con corrección ρ)
# ─────────────────────────────────────────────────────────────────────────────

def dc_win_prob(
    home_att: float,
    away_att: float,
    home_def: float,   # >1 = defensa débil (más goles en contra)
    away_def: float,
    home_adv: float,
    rho: float,
    max_goals: int = 10
) -> Tuple[float, float, float]:
    """
    Calcula P(home_win), P(draw), P(away_win) con Dixon-Coles.

    El modelo:
      λ_home = home_adv * attack_home * defense_away
      λ_away = attack_away * defense_home
      P_low_score = (1 - ρ*λ_home*λ_away)  ← corrección para 0-0, 1-0, 0-1, 1-1

    Returns: (prob_home, prob_draw, prob_away)
    """
    # Parámetros esperados
    exp_home = home_adv * home_att / away_def
    exp_away = away_att / home_def

    # Corriger para underestimation de scorelines bajos
    # ρ > 0 → aumenta probabilidad de 0-0, 1-1
    rho_factor = max(-0.5, min(0.5, rho))  # bound ρ

    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for h in range(max_goals):
        for a in range(max_goals):
            p = poisson_pmf(h, exp_home) * poisson_pmf(a, exp_away)

            # Aplicar corrección Dixon-Coles τ(μ) solo a scorelines bajos
            if h <= 1 and a <= 1:
                tau = 1.0 - rho_factor * (exp_home * exp_away)
                p *= max(0.0, tau)

            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

    # Normalizar (por si hay rounding errors)
    total = home_win + draw + away_win
    if total > 0:
        home_win /= total; draw /= total; away_win /= total

    return home_win, draw, away_win


def score_line_prob(
    home_att: float,
    away_att: float,
    home_def: float,
    away_def: float,
    home_adv: float,
    rho: float,
    max_goals: int = 8
) -> Dict[Tuple[int, int], float]:
    """Retorna dict {(h, a): prob} para las scorelines más probables."""
    exp_home = home_adv * home_att / away_def
    exp_away = away_att / home_def

    probs = {}
    for h in range(max_goals):
        for a in range(max_goals):
            p = poisson_pmf(h, exp_home) * poisson_pmf(a, exp_away)
            if h <= 1 and a <= 1:
                tau = 1.0 - rho_factor_dc(h, a, exp_home, exp_away, rho)
                p *= max(0.0, tau)
            if p > 0.0001:
                probs[(h, a)] = p

    return probs


def rho_factor_dc(h: int, a: int, exp_h: float, exp_a: float, rho: float) -> float:
    """Factor τ(μ) de Dixon-Coles para scoreline (h,a)."""
    if h <= 1 and a <= 1:
        return 1.0 - rho * exp_h * exp_a
    return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# MODEL FITTING (simplified, paraSeasoncontext)
# ─────────────────────────────────────────────────────────────────────────────

def fit_dixon_coles(
    conn: sqlite3.Connection,
    season_id: int,
    league_id: int = 743,
    decay: float = 0.9995
) -> Optional[Dict[str, Any]]:
    """
    Estima parámetros del modelo Dixon-Coles con los partidos de la temporada.

    Usa método de momentos simplificado:
    1. Estima λ_home y λ_away promedio de la liga
    2. Estima attack/defense relativo por equipo
    3. Estima ρ (parámetro de corrección)

    Args:
        decay: peso de decay por día (para dar más peso a partidos recientes)
    """
    # Obtener partidos de la temporada actual
    rows = conn.execute("""
        SELECT f.home_team_id, f.away_team_id, f.home_score, f.away_score,
               f.starting_at
        FROM fixtures f
        WHERE f.season_id = ?
          AND f.league_id = ?
          AND f.home_score IS NOT NULL
        ORDER BY f.starting_at
    """, (season_id, league_id)).fetchall()

    # Si no hay datos suficientes en la temporada actual, usar histórico (últimas N temporadas)
    if len(rows) < 10:
        rows = conn.execute("""
            SELECT f.home_team_id, f.away_team_id, f.home_score, f.away_score,
                   f.starting_at
            FROM fixtures f
            WHERE f.league_id = ?
              AND f.home_score IS NOT NULL
              AND f.season_id IN (
                  SELECT id FROM seasons
                  WHERE league_id = ?
                  ORDER BY start_date DESC LIMIT 5
              )
            ORDER BY f.starting_at
        """, (league_id, league_id)).fetchall()
        using_historical = True
    else:
        using_historical = False

    if len(rows) < 10:
        return None

    # Promedios generales
    total_h = sum(r[2] for r in rows)
    total_a = sum(r[3] for r in rows)
    n = len(rows)

    league_avg_h = total_h / n
    league_avg_a = total_a / n
    league_avg = (total_h + total_a) / (2 * n)

    # Promedio de home goals por partido (debería ser ~1.35 en fútbol)
    overall_avg = (total_h + total_a) / n  # ~2.65 para MX

    # Home advantage global
    home_advantage = league_avg_h / league_avg_a if league_avg_a > 0 else 1.05

    # Estimar attack y defense por equipo
    teams = set()
    for r in rows:
        teams.add(r[0]); teams.add(r[1])

    team_stats: Dict[int, Dict] = {t: {'gf': 0, 'ga': 0, 'home_games': 0, 'away_games': 0,
                                        'home_gf': 0, 'home_ga': 0, 'away_gf': 0, 'away_ga': 0}
                                    for t in teams}

    for home_id, away_id, home_score, away_score, _ in rows:
        team_stats[home_id]['home_games'] += 1
        team_stats[away_id]['away_games'] += 1
        team_stats[home_id]['gf'] += home_score; team_stats[home_id]['ga'] += away_score
        team_stats[away_id]['gf'] += away_score; team_stats[away_id]['ga'] += home_score
        team_stats[home_id]['home_gf'] += home_score; team_stats[home_id]['home_ga'] += away_score
        team_stats[away_id]['away_gf'] += away_score; team_stats[away_id]['away_ga'] += home_score

    # Attack y Defense como ratio vs promedio de liga
    home_params = {}
    away_params = {}

    for team_id, stats in team_stats.items():
        # Home: λ = home_adv * attack * defense_opp
        # avg_gf_home = home_adv * attack_team * avg_def_opp
        # attack_team = avg_gf_home / (home_adv * avg_def_opp)
        avg_gf_home = stats['home_gf'] / stats['home_games'] if stats['home_games'] > 0 else 0.0
        avg_gf_away = stats['away_gf'] / stats['away_games'] if stats['away_games'] > 0 else 0.0
        avg_ga_home = stats['home_ga'] / stats['home_games'] if stats['home_games'] > 0 else 0.0
        avg_ga_away = stats['away_ga'] / stats['away_games'] if stats['away_games'] > 0 else 0.0

        # Normalized attack (1.0 = average team)
        attack = (avg_gf_home / league_avg_h + avg_gf_away / league_avg_a) / 2.0 if league_avg_h > 0 else 1.0
        # Defense: goals conceded ratio (lower = better)
        # avg_ga vs league_avg_a
        defense = (avg_ga_home / league_avg_a + avg_ga_away / league_avg_h) / 2.0 if league_avg_a > 0 else 1.0

        # Bound attack and defense
        attack = max(0.3, min(2.5, attack))
        defense = max(0.3, min(2.5, defense))

        home_params[team_id] = attack
        away_params[team_id] = attack  # simplified: same attack home/away
        # Defense is per team (lower = better defense)
        # We store it separately

    # Re-derive defense properly
    # defense_team = avg_goles_recibidos_como_local / avg_goles_recibidos_local_liga
    defense_params = {}
    for team_id, stats in team_stats.items():
        avg_ga = (stats['ga'] / (stats['home_games'] + stats['away_games'])) if (stats['home_games'] + stats['away_games']) > 0 else league_avg_a
        def_param = avg_ga / league_avg_a if league_avg_a > 0 else 1.0
        defense_params[team_id] = max(0.3, min(2.5, def_param))

    # Estimar ρ (Dixon-Coles correlation parameter)
    # Como proxy, usamos la frecuencia observed de 0-0 y 1-1 vs Poisson
    n_00 = sum(1 for r in rows if r[2] == 0 and r[3] == 0)
    n_11 = sum(1 for r in rows if r[2] == 1 and r[3] == 1)
    n_low = sum(1 for r in rows if r[2] <= 1 and r[3] <= 1)

    # Poisson predicho para 0-0
    p_00_poisson = poisson_pmf(0, league_avg_h) * poisson_pmf(0, league_avg_a)
    p_11_poisson = poisson_pmf(1, league_avg_h) * poisson_pmf(1, league_avg_a)
    p_low_poisson = sum(
        poisson_pmf(h, league_avg_h) * poisson_pmf(a, league_avg_a)
        for h in range(2) for a in range(2)
    )

    observed_low = n_low / n
    poisson_low = p_low_poisson

    # ρ estima la discrepancia (positive = Poisson subestima draws/low scores)
    if poisson_low > 0.01:
        rho = (observed_low - poisson_low) / poisson_low * 0.1
    else:
        rho = 0.0

    rho = max(-0.3, min(0.3, rho))  # bound

    return {
        'home_attack': home_params,
        'away_attack': home_params,  # same for this simplified version
        'defense': defense_params,
        'home_advantage': home_advantage,
        'rho': rho,
        'league_avg_home_goals': league_avg_h,
        'league_avg_away_goals': league_avg_a,
        'league_avg_goals': league_avg,
        'n_matches': n,
        'season_id': season_id,
    }


def predict_from_model(
    model: Dict[str, Any],
    home_team_id: int,
    away_team_id: int,
    home_altitude_m: float = 0,
    away_altitude_m: float = 0,
    rest_diff: float = 0,  # days more rest for home
    form_momentum_diff: float = 0,  # home momentum - away momentum
    h2h_home_win_rate: float = 0.5,
    max_goals: int = 8
) -> Dict[str, Any]:
    """
    Genera predicción completa desde el modelo Dixon-Coles + ajustes.

    Args:
        model: output de fit_dixon_coles
        home_team_id, away_team_id: IDs de equipos
        home_altitude_m, away_altitude_m: altitud del estadio local/visitante
        rest_diff: diferencia de días de descanso (home - away)
        form_momentum_diff: diferencia de momentum (home - away) normalizado
        h2h_home_win_rate: porcentaje de victorias del local en H2H

    Returns:
        {
            'home_win': float,
            'draw': float,
            'away_win': float,
            'predicted_home_goals': float,
            'predicted_away_goals': float,
            'most_likely_score': (int, int),
            'score_probs': dict,
            'both_score': float,
            'over_2_5': float,
            'under_2_5': float,
            'model_confidence': float,  # 0-1
            'model_name': 'Dixon-Coles',
        }
    """
    home_att = model['home_attack'].get(home_team_id, 1.0)
    away_att = model['away_attack'].get(away_team_id, 1.0)
    home_def = model['defense'].get(home_team_id, 1.0)
    away_def = model['defense'].get(away_team_id, 1.0)

    # ── Ajustes heurísticos sobre λ ───────────────────────────────────────

    # Ajuste por altitud: equipos de CDMX/Toluca/Pachuca (2400m+) anotan +0.15 λ extra en casa
    altitude_adj = 0.0
    if home_altitude_m >= 2400:
        altitude_adj += 0.12
    elif home_altitude_m >= 2000:
        altitude_adj += 0.06
    # Visitante viene de baja altitud → penalización
    if home_altitude_m - away_altitude_m >= 2000:
        altitude_adj += 0.08

    # Ajuste por descanso: cada día extra de descanso ≈ +0.03 a λ local
    rest_adj = 0.03 * max(-3, min(5, rest_diff))

    # Ajuste por momentum (forma reciente vs promedio)
    # Si el equipo viene en racha, su attack efectivo sube
    momentum_adj = 0.05 * max(-1.5, min(1.5, form_momentum_diff))

    # Ajuste por H2H (si hay clear pattern)
    if h2h_home_win_rate > 0.65:
        # El local domina el H2H → sube λ local
        h2h_adj = 0.05 * (h2h_home_win_rate - 0.5)
    elif h2h_home_win_rate < 0.35:
        h2h_adj = 0.05 * (h2h_home_win_rate - 0.5)
    else:
        h2h_adj = 0.0

    # Ajustes combinados
    total_adj = 1.0 + altitude_adj + rest_adj + momentum_adj + h2h_adj
    total_adj = max(0.5, min(1.6, total_adj))

    exp_home = total_adj * model['home_advantage'] * home_att / away_def
    exp_away = (1.0 / total_adj) * away_att / home_def if home_def > 0 else away_att

    # Bound expected goals
    exp_home = max(0.2, min(4.5, exp_home))
    exp_away = max(0.2, min(4.5, exp_away))

    # ── Probabilidades 1X2 ────────────────────────────────────────────────
    home_win, draw, away_win = dc_win_prob(
        home_att, away_att,
        home_def, away_def,
        model['home_advantage'] * total_adj,
        model['rho'],
        max_goals
    )

    # ── Scorelines ───────────────────────────────────────────────────────
    score_probs = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson_pmf(h, exp_home) * poisson_pmf(a, exp_away)
            if h <= 1 and a <= 1:
                p *= max(0.0, 1.0 - model['rho'] * exp_home * exp_away)
            if p > 0.0005:
                score_probs[(h, a)] = p

    # ── Goals markets ────────────────────────────────────────────────────
    both_score = sum(p for (h, a), p in score_probs.items() if h > 0 and a > 0)
    over_2_5 = sum(p for (h, a), p in score_probs.items() if h + a > 2)
    under_2_5 = 1.0 - over_2_5

    # ── Most likely score ────────────────────────────────────────────────
    most_likely = max(score_probs, key=score_probs.get)
    predicted_home = round(exp_home, 2)
    predicted_away = round(exp_away, 2)

    # ── Confidence ───────────────────────────────────────────────────────
    # Basada en: sample size del modelo + discrepancia entre modeloy cuotas implícitas
    n_matches = model.get('n_matches', 0)
    model_confidence = min(0.85, 0.45 + 0.005 * n_matches)

    # Reducir confianza si los ajustes heurísticos son grandes
    if abs(total_adj - 1.0) > 0.15:
        model_confidence *= 0.85

    return {
        'home_win': round(home_win, 4),
        'draw': round(draw, 4),
        'away_win': round(away_win, 4),
        'predicted_home_goals': predicted_home,
        'predicted_away_goals': predicted_away,
        'most_likely_score': most_likely,
        'most_likely_score_prob': round(score_probs.get(most_likely, 0), 4),
        'score_probs': {f"{h}-{a}": round(p, 4) for (h, a), p in
                       list(sorted(score_probs.items(), key=lambda x: -x[1]))[:15]},
        'both_score': round(both_score, 4),
        'over_2_5': round(over_2_5, 4),
        'under_2_5': round(under_2_5, 4),
        'model_confidence': round(model_confidence, 3),
        'model_name': 'Dixon-Coles v1',
        'expected_goals_adj': round(total_adj, 3),
        # raw sin ajustes heurísticos
        'exp_home_raw': round(model['home_advantage'] * home_att / away_def, 2),
        'exp_away_raw': round(away_att / home_def, 2),
    }
