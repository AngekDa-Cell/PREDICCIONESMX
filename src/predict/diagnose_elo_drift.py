"""
diagnose_elo_drift.py — Diagnostica drift entre Elo rating y win rate real.

Para un equipo dado:
- Calcula Elo actual (después de todos los partidos)
- Calcula win rate histórico (local vs visitante)
- Compara la "implied win rate" del Elo vs el real

Útil para encontrar equipos sobrevalorados por el Elo.

Uso:
  python3 src/predict/diagnose_elo_drift.py --team "Cruz Azul"
  python3 src/predict/diagnose_elo_drift.py --team "Pumas"
  python3 src/predict/diagnose_elo_drift.py --all
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.elo import (
    EloState, ELO_BASE, HOME_ADVANTAGE_ELO, expected_score
)


def build_elo_state(conn: sqlite3.Connection, league_id: int = 743) -> EloState:
    """Construye Elo state desde todos los partidos."""
    state = EloState()
    state.update_all(conn, league_id=league_id)
    return state


def get_team_stats(conn: sqlite3.Connection, team_id: int) -> Dict[str, Any]:
    """Calcula win rate local y visitante histórico."""
    rows = conn.execute("""
        SELECT
            home_team_id, away_team_id,
            home_score, away_score,
            starting_at
        FROM fixtures
        WHERE league_id = 743
          AND home_score IS NOT NULL
          AND (home_team_id = ? OR away_team_id = ?)
        ORDER BY starting_at
    """, (team_id, team_id)).fetchall()

    home_n = home_w = home_d = home_l = 0
    away_n = away_w = away_d = away_l = 0

    for r in rows:
        if r['home_team_id'] == team_id:
            home_n += 1
            if r['home_score'] > r['away_score']:
                home_w += 1
            elif r['home_score'] < r['away_score']:
                home_l += 1
            else:
                home_d += 1
        else:
            away_n += 1
            if r['away_score'] > r['home_score']:
                away_w += 1
            elif r['away_score'] < r['home_score']:
                away_l += 1
            else:
                away_d += 1

    return {
        'home_n': home_n,
        'home_w': home_w, 'home_d': home_d, 'home_l': home_l,
        'home_win_rate': home_w / home_n if home_n else 0,
        'away_n': away_n,
        'away_w': away_w, 'away_d': away_d, 'away_l': away_l,
        'away_win_rate': away_w / away_n if away_n else 0,
    }


def get_team_id(conn: sqlite3.Connection, name: str) -> int:
    """Busca equipo por nombre (case-insensitive)."""
    row = conn.execute("""
        SELECT id, name FROM teams
        WHERE LOWER(name) LIKE ?
        LIMIT 1
    """, (f"%{name.lower()}%",)).fetchone()
    return row['id'] if row else None


def diagnose_team(conn: sqlite3.Connection, team_id: int, team_name: str) -> Dict[str, Any]:
    """Diagnóstico completo de un equipo."""
    # Construir Elo state
    elo_state = build_elo_state(conn)
    elo = elo_state.get(team_id)

    # Stats reales
    stats = get_team_stats(conn, team_id)

    # Expected score vs Elo "promedio" (1500) en casa
    expected_home = expected_score(elo, 1500, HOME_ADVANTAGE_ELO)
    expected_away = expected_score(elo, 1500, 0)

    # Diferencia entre Elo implied y real
    home_drift = expected_home - stats['home_win_rate']
    away_drift = expected_away - stats['away_win_rate']

    # Rating comparación con el promedio
    elo_vs_avg = elo - ELO_BASE

    return {
        'team': team_name,
        'team_id': team_id,
        'elo_rating': round(elo, 1),
        'elo_vs_avg': round(elo_vs_avg, 1),
        'expected_home_win_rate': round(expected_home, 4),
        'expected_away_win_rate': round(expected_away, 4),
        'real_home_win_rate': round(stats['home_win_rate'], 4),
        'real_away_win_rate': round(stats['away_win_rate'], 4),
        'home_drift': round(home_drift, 4),
        'away_drift': round(away_drift, 4),
        'n_home': stats['home_n'],
        'n_away': stats['away_n'],
        'diagnosis': (
            "✅ OK" if abs(home_drift) < 0.05 and abs(away_drift) < 0.05 else
            f"⚠️ SOBREESTIMADO local (+{home_drift:.1%})" if home_drift > 0.10 else
            f"⚠️ SUBESTIMADO local ({home_drift:.1%})" if home_drift < -0.10 else
            f"⚠️ SOBREESTIMADO visitante (+{away_drift:.1%})" if away_drift > 0.10 else
            f"⚠️ SUBESTIMADO visitante ({away_drift:.1%})" if away_drift < -0.10 else
            "🟡 drift menor"
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", help="Nombre del equipo")
    parser.add_argument("--all", action="store_true", help="Diagnosticar todos los equipos")
    args = parser.parse_args()

    DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if args.all:
        # Diagnosticar todos
        teams = conn.execute("""
            SELECT DISTINCT t.id, t.name FROM teams t
            JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
            WHERE f.league_id = 743
        """).fetchall()

        results = []
        for t in teams:
            diag = diagnose_team(conn, t['id'], t['name'])
            results.append(diag)

        # Ordenar por drift visitante (peor primero)
        results.sort(key=lambda x: x['away_drift'], reverse=True)

        print("=" * 90)
        print("📊 DIAGNÓSTICO DE DRIFT ELO vs WIN RATE REAL")
        print("=" * 90)
        print(f"{'Equipo':<25} {'Elo':>7} {'ExpL':>7} {'RealL':>7} {'DriftL':>8} {'ExpV':>7} {'RealV':>7} {'DriftV':>8} {'Status':<30}")
        print("-" * 90)

        for r in results:
            print(f"{r['team']:<25} {r['elo_rating']:>7.1f} "
                  f"{r['expected_home_win_rate']:>6.1%} {r['real_home_win_rate']:>6.1%} "
                  f"{r['home_drift']:>+7.1%} "
                  f"{r['expected_away_win_rate']:>6.1%} {r['real_away_win_rate']:>6.1%} "
                  f"{r['away_drift']:>+7.1%} "
                  f"{r['diagnosis']:<30}")

        # Guardar
        out_path = PROJECT_ROOT / "data" / "elo_drift_diagnosis.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({"generated_at": str(Path(__file__).stat().st_mtime), "teams": results}, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Diagnóstico guardado en {out_path}")

    elif args.team:
        team_id = get_team_id(conn, args.team)
        if not team_id:
            print(f"❌ Equipo no encontrado: {args.team}")
            return

        team_name = conn.execute("SELECT name FROM teams WHERE id = ?", (team_id,)).fetchone()['name']
        diag = diagnose_team(conn, team_id, team_name)

        print("=" * 70)
        print(f"📊 DIAGNÓSTICO: {diag['team']}")
        print("=" * 70)
        print(f"Elo rating actual:      {diag['elo_rating']:>7.1f}  (vs promedio {ELO_BASE})")
        print(f"  Diferencia vs avg:     {diag['elo_vs_avg']:>+7.1f}")
        print()
        print(f"COMO LOCAL ({diag['n_home']} partidos):")
        print(f"  Win rate esperado Elo: {diag['expected_home_win_rate']:>6.1%}")
        print(f"  Win rate real:         {diag['real_home_win_rate']:>6.1%}")
        print(f"  Drift:                 {diag['home_drift']:>+6.1%}")
        print()
        print(f"COMO VISITANTE ({diag['n_away']} partidos):")
        print(f"  Win rate esperado Elo: {diag['expected_away_win_rate']:>6.1%}")
        print(f"  Win rate real:         {diag['real_away_win_rate']:>6.1%}")
        print(f"  Drift:                 {diag['away_drift']:>+6.1%}")
        print()
        print(f"Status: {diag['diagnosis']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()