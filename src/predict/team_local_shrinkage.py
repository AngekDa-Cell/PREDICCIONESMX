"""
team_local_shrinkage.py — Calcula shrinkage por equipo y localía.

Problema: el Elo rating global está sobreestimado, pero no uniforme.
Cruz Azul visitante: drift +38%
Pumas local: drift +30%
Santos Laguna local: drift -4% (infrarvalorizado!)

Solución: shrinkage específico por equipo y rol (local/visitante)
  shrinkage_X_local = 0.5 + 0.5 * (real_home_wr / expected_home_wr)
  shrinkage_X_visit = 0.5 + 0.5 * (real_away_wr / expected_away_wr)

Walk-forward: para cada partido de test, calcula el shrinkage usando
solo partidos ANTERIORES (evita look-ahead bias).

Uso:
  python3 src/predict/team_local_shrinkage.py --compute --start 2025-01-01 --end 2025-12-31
  python3 src/predict/team_local_shrinkage.py --apply
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.elo import (
    EloState, ELO_BASE, HOME_ADVANTAGE_ELO, expected_score
)


# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULO DE SHRINKAGE POR EQUIPO
# ─────────────────────────────────────────────────────────────────────────────

def calculate_team_shrinkage(
    conn: sqlite3.Connection,
    team_id: int,
    before_date: str,
    min_games: int = 10,
    league_id: int = 743,
) -> Dict[str, Any]:
    """
    Calcula shrinkage específico para un equipo basado en histórico ANTES de before_date.

    Returns:
        Dict con shrinkage_local, shrinkage_visit, stats detalladas
    """
    # Construir Elo state con partidos antes de before_date
    state = EloState()
    rows = conn.execute("""
        SELECT home_team_id, away_team_id, home_score, away_score, starting_at
        FROM fixtures
        WHERE league_id = ?
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND starting_at < ?
        ORDER BY starting_at
    """, (league_id, before_date)).fetchall()

    for r in rows:
        state.update_match(r['home_team_id'], r['away_team_id'], r['home_score'], r['away_score'])

    elo = state.get(team_id)

    # Expected win rates del Elo (vs promedio 1500)
    exp_home = expected_score(elo, 1500, HOME_ADVANTAGE_ELO)
    exp_away = expected_score(elo, 1500, 0)

    # Win rates reales (de los mismos partidos)
    team_rows = conn.execute("""
        SELECT home_team_id, away_team_id, home_score, away_score
        FROM fixtures
        WHERE league_id = ?
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND starting_at < ?
          AND (home_team_id = ? OR away_team_id = ?)
    """, (league_id, before_date, team_id, team_id)).fetchall()

    home_n = home_w = 0
    away_n = away_w = 0

    for r in team_rows:
        if r['home_team_id'] == team_id:
            home_n += 1
            if r['home_score'] > r['away_score']:
                home_w += 1
        else:
            away_n += 1
            if r['away_score'] > r['home_score']:
                away_w += 1

    if home_n < min_games or away_n < min_games:
        return {
            "team_id": team_id,
            "shrinkage_local": 1.0,
            "shrinkage_visit": 1.0,
            "valid": False,
            "reason": f"too_few_games (home={home_n}, away={away_n})",
        }

    real_home = home_w / home_n
    real_away = away_w / away_n

    # Calcular shrinkage
    # shrinkage = 0.5 + 0.5 * (real / expected)
    # Si real == expected → shrinkage = 1.0 (sin cambio)
    # Si real < expected → shrinkage < 1.0 (más contracción)
    # Si real > expected → shrinkage > 1.0 (menos contracción)
    if exp_home > 0.1:
        shrink_home = 0.5 + 0.5 * (real_home / exp_home)
    else:
        shrink_home = 1.0

    if exp_away > 0.1:
        shrink_away = 0.5 + 0.5 * (real_away / exp_away)
    else:
        shrink_away = 1.0

    # Clamp [0.3, 1.5] para evitar valores extremos
    shrink_home = max(0.3, min(1.5, shrink_home))
    shrink_away = max(0.3, min(1.5, shrink_away))

    return {
        "team_id": team_id,
        "elo": round(elo, 1),
        "exp_home_wr": round(exp_home, 4),
        "exp_away_wr": round(exp_away, 4),
        "real_home_wr": round(real_home, 4),
        "real_away_wr": round(real_away, 4),
        "home_drift": round(exp_home - real_home, 4),
        "away_drift": round(exp_away - real_away, 4),
        "shrinkage_local": round(shrink_home, 3),
        "shrinkage_visit": round(shrink_away, 3),
        "n_home": home_n,
        "n_away": away_n,
        "valid": True,
    }


def compute_all_team_shrinkages(
    conn: sqlite3.Connection,
    before_date: str,
    min_games: int = 10,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Calcula shrinkage para todos los equipos que han jugado antes de before_date.
    """
    teams = conn.execute("""
        SELECT DISTINCT t.id, t.name FROM teams t
        JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
        WHERE f.league_id = 743 AND f.starting_at < ?
    """, (before_date,)).fetchall()

    results = {}
    for t in teams:
        shrink = calculate_team_shrinkage(conn, t['id'], before_date, min_games)
        if shrink.get("valid", False):
            results[t['name']] = shrink

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump({
                "computed_at": before_date,
                "n_teams": len(results),
                "teams": results,
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ Shrinkage por equipo guardado en {output_path}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# APLICACIÓN DEL SHRINKAGE
# ─────────────────────────────────────────────────────────────────────────────

def predict_with_local_shrinkage(
    elo_state: EloState,
    home_id: int,
    away_id: int,
    team_shrinkages: Dict[str, Any],
    global_shrinkage: float = 1.0,
) -> Dict[str, Any]:
    """
    Predicción Elo con shrinkage por equipo Y global.

    Proceso:
    1. Aplica shrinkage global a todos los Elo
    2. Aplica shrinkage específico del equipo (local/visitante)
    3. Combina: final_elo = global_shrink * team_shrink * (elo - base) + base

    Args:
        elo_state: EloState construido con todos los partidos
        home_id, away_id: IDs de equipos
        team_shrinkages: dict {team_id: {shrinkage_local, shrinkage_visit, ...}}
        global_shrinkage: shrinkage global base (default 1.0 = sin shrinkage)
    """
    home_elo_raw = elo_state.get(home_id)
    away_elo_raw = elo_state.get(away_id)

    # Shrinkage específico del equipo
    home_team_shrink = team_shrinkages.get(str(home_id), team_shrinkages.get(home_id, {}))
    away_team_shrink = team_shrinkages.get(str(away_id), team_shrinkages.get(away_id, {}))

    shrink_local_home = home_team_shrink.get("shrinkage_local", 1.0)
    shrink_visit_away = away_team_shrink.get("shrinkage_visit", 1.0)

    # Combinación: shrinkage compuesto = global * team
    home_shrink_final = global_shrinkage * shrink_local_home
    away_shrink_final = global_shrinkage * shrink_visit_away

    # Aplicar
    home_elo_adj = ELO_BASE + (home_elo_raw - ELO_BASE) * home_shrink_final
    away_elo_adj = ELO_BASE + (away_elo_raw - ELO_BASE) * away_shrink_final

    # Predicción 1X2 via distribución Poisson
    elo_diff = (home_elo_adj + HOME_ADVANTAGE_ELO) - away_elo_adj
    lam_home = max(0.3, 1.5 + elo_diff / 200.0)
    lam_away = max(0.3, 1.5 - elo_diff / 200.0)

    from math import exp, log, lgamma
    def poisson_pmf(k, lam):
        return exp(k * log(lam) - lam - lgamma(k + 1))

    home_win = draw = away_win = 0.0
    for h in range(7):
        for a in range(7):
            p = poisson_pmf(h, lam_home) * poisson_pmf(a, lam_away)
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

    total = home_win + draw + away_win

    return {
        "home_win": home_win / total,
        "draw": draw / total,
        "away_win": away_win / total,
        "home_elo_raw": round(home_elo_raw, 1),
        "away_elo_raw": round(away_elo_raw, 1),
        "home_elo_adj": round(home_elo_adj, 1),
        "away_elo_adj": round(away_elo_adj, 1),
        "home_shrink_total": round(home_shrink_final, 3),
        "away_shrink_total": round(away_shrink_final, 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compute", action="store_true", help="Calcular shrinkage por equipo")
    parser.add_argument("--show", action="store_true", help="Mostrar shrinkage calculado")
    parser.add_argument("--start", default="2025-01-01", help="Fecha desde la cual calcular")
    parser.add_argument("--min-games", type=int, default=10)
    args = parser.parse_args()

    DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if args.compute:
        output_path = PROJECT_ROOT / "data" / "team_local_shrinkage.json"
        results = compute_all_team_shrinkages(conn, args.start, args.min_games, output_path)
        print(f"📊 {len(results)} equipos con shrinkage válido")

    elif args.show:
        path = PROJECT_ROOT / "data" / "team_local_shrinkage.json"
        if not path.exists():
            print(f"❌ No existe {path}. Corre con --compute primero.")
            return
        with open(path) as f:
            data = json.load(f)

        print(f"📊 Shrinkage por equipo (computado en {data.get('computed_at')}):")
        print("=" * 90)
        print(f"{'Equipo':<25} {'Elo':>6} {'ShrinkL':>8} {'ShrinkV':>8} {'DriftL':>7} {'DriftV':>7}")
        print("-" * 90)

        teams_sorted = sorted(data["teams"].values(),
                              key=lambda x: x.get("away_drift", 0), reverse=True)
        for t in teams_sorted:
            print(f"{t['team_id']:<25} {t['elo']:>6.0f} "
                  f"{t['shrinkage_local']:>8.2f} {t['shrinkage_visit']:>8.2f} "
                  f"{t['home_drift']:>+6.1%} {t['away_drift']:>+6.1%}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()