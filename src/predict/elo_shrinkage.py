"""
elo_shrinkage.py — Ajusta Elo rating para corregir drift sistemático.

Problema: El Elo rating de los equipos Liga MX está sistemáticamente
sobreestimado vs win rate real. El drift promedio es +25% (modelo dice
75% win rate, realidad es 50%).

Causa probable:
1. K-factor muy alto → ratings se mueven rápido y no se estabilizan
2. Sin time-decay → partidos antiguos pesan igual que recientes
3. Liga con mucha paridad → equipos fluctúan pero Elo no se contrae

Solución: SHRINKAGE hacia el promedio.
  adjusted_elo = 1500 + (elo - 1500) * shrinkage_factor

Donde shrinkage_factor ∈ [0, 1]:
- 1.0 = sin cambios (Elo original)
- 0.5 = ratings a la mitad hacia 1500
- 0.0 = todos en 1500 (sin señal)

Encuentra shrinkage_factor óptimo via grid search sobre backtest.

Uso:
  python3 src/predict/elo_shrinkage.py --optimize
  python3 src/predict/elo_shrinkage.py --factor 0.6
"""
import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.elo import (
    EloState, ELO_BASE, HOME_ADVANTAGE_ELO, expected_score
)


# ─────────────────────────────────────────────────────────────────────────────
# SHRINKAGE
# ─────────────────────────────────────────────────────────────────────────────

def apply_shrinkage(elo: float, factor: float, anchor: float = ELO_BASE) -> float:
    """
    Aplica shrinkage al Elo: contrae hacia anchor (default 1500).

    Args:
        elo: Elo rating actual
        factor: factor de shrinkage [0, 1]
        anchor: rating objetivo (default 1500 = promedio)

    Returns:
        Elo ajustado
    """
    return anchor + (elo - anchor) * factor


def predict_match_elo(
    elo_state: EloState,
    home_id: int,
    away_id: int,
    shrinkage: float = 1.0,
) -> Dict[str, float]:
    """
    Predicción 1X2 usando Elo (con shrinkage opcional).
    Usa distribución Poisson para modelar varianza.
    """
    elo_h = apply_shrinkage(elo_state.get(home_id), shrinkage)
    elo_a = apply_shrinkage(elo_state.get(away_id), shrinkage)

    # E_home con HA
    eh = expected_score(elo_h, elo_a, HOME_ADVANTAGE_ELO)
    ea = 1 - eh

    # Diferencia Elo para λ Poisson
    elo_diff = (elo_h + HOME_ADVANTAGE_ELO) - elo_a
    # Convertir diferencia a goles esperados (aprox)
    # 100 Elo ≈ 0.5 goles
    lam_home = 1.5 + elo_diff / 200.0
    lam_away = 1.5 - elo_diff / 200.0
    lam_home = max(0.3, lam_home)
    lam_away = max(0.3, lam_away)

    # P(home), P(draw), P(away) via Poisson
    from math import exp, log
    def poisson_pmf(k, lam):
        return exp(k * log(lam) - lam - sum(log(i) for i in range(1, k+1)))

    # Calcular distribución de Poisson para cada lado
    p_home = p_draw = p_away = 0.0
    for h in range(7):
        for a in range(7):
            p = poisson_pmf(h, lam_home) * poisson_pmf(a, lam_away)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p

    # Normalizar
    total = p_home + p_draw + p_away
    return {
        "home_win": p_home / total,
        "draw": p_draw / total,
        "away_win": p_away / total,
        "elo_home": elo_h,
        "elo_away": elo_a,
        "lam_home": lam_home,
        "lam_away": lam_away,
    }


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST PARA ENCONTRAR FACTOR ÓPTIMO
# ─────────────────────────────────────────────────────────────────────────────

def build_elo_with_decay(conn: sqlite3.Connection, decay: float = 1.0, league_id: int = 743) -> EloState:
    """
    Construye Elo state con time-decay opcional.

    Args:
        decay: factor de decay temporal [0, 1]
            1.0 = sin decay (todos los partidos pesan igual)
            0.95 = cada partido anterior pesa 0.95× (decay exponencial)
            0.0 = solo cuenta el último partido

    Si decay < 1.0, reduce K-factor en partidos antiguos.
    """
    state = EloState()

    rows = conn.execute("""
        SELECT home_team_id, away_team_id, home_score, away_score, starting_at
        FROM fixtures
        WHERE league_id = ?
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
        ORDER BY starting_at
    """, (league_id,)).fetchall()

    from predict.elo import ELO_K_FACTOR, k_multiplier, actual_score

    for i, row in enumerate(rows):
        rh = state.get(row['home_team_id'])
        ra = state.get(row['away_team_id'])

        eh = expected_score(rh, ra, HOME_ADVANTAGE_ELO)
        ea = 1 - eh

        sh, sa = actual_score(row['home_score'], row['away_score'])

        goal_diff = abs(row['home_score'] - row['away_score'])
        km = k_multiplier(goal_diff)

        # Si hay decay, partidos más antiguos tienen menos peso
        if decay < 1.0:
            # Decay exponencial: partidos más recientes (i cercano a len) pesan más
            weight = decay ** (len(rows) - 1 - i)
            k = ELO_K_FACTOR * km * weight
        else:
            k = ELO_K_FACTOR * km

        state.ratings[row['home_team_id']] = rh + k * (sh - eh)
        state.ratings[row['away_team_id']] = ra + k * (sa - ea)

    return state


def backtest_shrinkage(
    conn: sqlite3.Connection,
    shrinkage: float,
    decay: float = 1.0,
    test_start: str = "2025-01-01",
    test_end: str = "2025-12-31",
    league_id: int = 743,
) -> Dict[str, Any]:
    """
    Backtest del Elo con shrinkage y/o decay dados.
    Walk-forward: para cada partido de test, calcula Elo sin ver el resultado.
    """
    # Construir Elo state con todos los partidos hasta test_start
    state = EloState()

    # Primero: ingestar todos los partidos antes de test_start
    train_rows = conn.execute("""
        SELECT home_team_id, away_team_id, home_score, away_score, starting_at
        FROM fixtures
        WHERE league_id = ?
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND starting_at < ?
        ORDER BY starting_at
    """, (league_id, test_start)).fetchall()

    from predict.elo import ELO_K_FACTOR, k_multiplier, actual_score

    for i, row in enumerate(train_rows):
        rh = state.get(row['home_team_id'])
        ra = state.get(row['away_team_id'])

        eh = expected_score(rh, ra, HOME_ADVANTAGE_ELO)
        ea = 1 - eh

        sh, sa = actual_score(row['home_score'], row['away_score'])

        goal_diff = abs(row['home_score'] - row['away_score'])
        km = k_multiplier(goal_diff)

        if decay < 1.0:
            weight = decay ** (len(train_rows) - 1 - i)
            k = ELO_K_FACTOR * km * weight
        else:
            k = ELO_K_FACTOR * km

        state.ratings[row['home_team_id']] = rh + k * (sh - eh)
        state.ratings[row['away_team_id']] = ra + k * (sa - ea)

    # Walk-forward sobre test
    test_rows = conn.execute("""
        SELECT id, home_team_id, away_team_id, home_score, away_score, starting_at
        FROM fixtures
        WHERE league_id = ?
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND starting_at >= ?
          AND starting_at < ?
        ORDER BY starting_at
    """, (league_id, test_start, test_end)).fetchall()

    correct = 0
    brier_total = 0.0
    n = 0

    for row in test_rows:
        # Predicción con shrinkage
        pred = predict_match_elo(state, row['home_team_id'], row['away_team_id'], shrinkage)
        probs = [pred['home_win'], pred['draw'], pred['away_win']]

        # Actual
        if row['home_score'] > row['away_score']:
            actual = 0
        elif row['home_score'] < row['away_score']:
            actual = 2
        else:
            actual = 1

        if probs.index(max(probs)) == actual:
            correct += 1

        # Brier
        for i in range(3):
            target = 1.0 if i == actual else 0.0
            brier_total += (probs[i] - target) ** 2

        n += 1

        # Update Elo con el resultado real (walk-forward)
        rh = state.get(row['home_team_id'])
        ra = state.get(row['away_team_id'])
        eh = expected_score(rh, ra, HOME_ADVANTAGE_ELO)
        ea = 1 - eh
        sh, sa = actual_score(row['home_score'], row['away_score'])
        goal_diff = abs(row['home_score'] - row['away_score'])
        km = k_multiplier(goal_diff)
        k = ELO_K_FACTOR * km
        state.ratings[row['home_team_id']] = rh + k * (sh - eh)
        state.ratings[row['away_team_id']] = ra + k * (sa - ea)

    return {
        "shrinkage": shrinkage,
        "decay": decay,
        "n": n,
        "accuracy": correct / n if n else 0,
        "brier": brier_total / n if n else 0,
    }


def grid_search(
    conn: sqlite3.Connection,
    shrinkages: List[float],
    decays: List[float] = [1.0],
    test_start: str = "2025-01-01",
    test_end: str = "2025-12-31",
) -> List[Dict[str, Any]]:
    """Grid search sobre shrinkage × decay."""
    results = []
    for s in shrinkages:
        for d in decays:
            r = backtest_shrinkage(conn, s, d, test_start, test_end)
            results.append(r)
            print(f"  shrinkage={s:.2f} decay={d:.3f} → acc={r['accuracy']:.2%} brier={r['brier']:.4f} (n={r['n']})")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimize", action="store_true", help="Grid search del factor óptimo")
    parser.add_argument("--factor", type=float, help="Aplicar factor específico")
    parser.add_argument("--test-start", default="2025-01-01")
    parser.add_argument("--test-end", default="2025-12-31")
    args = parser.parse_args()

    DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if args.optimize:
        print("⏳ Grid search shrinkage factor...")
        shrinkages = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        decays = [1.0, 0.999, 0.995, 0.99]  # Decay variants
        results = grid_search(conn, shrinkages, decays, args.test_start, args.test_end)

        # Mejor por accuracy
        best = max(results, key=lambda r: r["accuracy"])
        print(f"\n🏆 MEJOR (por accuracy): shrinkage={best['shrinkage']:.2f} decay={best['decay']:.3f}")
        print(f"   accuracy={best['accuracy']:.2%} brier={best['brier']:.4f}")

        # Guardar
        out_path = PROJECT_ROOT / "data" / "elo_shrinkage_optimization.json"
        with open(out_path, "w") as f:
            json.dump({
                "test_start": args.test_start,
                "test_end": args.test_end,
                "results": results,
                "best": best,
            }, f, indent=2)
        print(f"\n✅ Resultados guardados en {out_path}")

    elif args.factor is not None:
        print(f"⏳ Backtest con shrinkage={args.factor}...")
        r = backtest_shrinkage(conn, args.factor, 1.0, args.test_start, args.test_end)
        print(f"  accuracy={r['accuracy']:.2%} brier={r['brier']:.4f} (n={r['n']})")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()