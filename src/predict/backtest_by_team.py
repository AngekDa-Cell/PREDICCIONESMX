"""
backtest_by_team.py — Diagnóstico de accuracy por equipo.

Identifica en qué equipos el modelo acierta más/menos.
Útil para detectar:
- Equipos sobrevalorados por el modelo
- Equipos infravalorados
- Equipos con alta varianza

Uso:
  python3 src/predict/backtest_by_team.py --start 2024-01-01 --end 2025-12-31
  python3 src/predict/backtest_by_team.py --last-n 200
"""
import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.backtest import predict_match
from predict.heuristics import load_manual_narratives
from predict.misc_utils import get_season_id_for_date


def get_actual_result(home_score: int, away_score: int) -> int:
    """0=home, 1=draw, 2=away."""
    if home_score > away_score:
        return 0
    elif home_score < away_score:
        return 2
    return 1


def brier_per_match(probs: List[float], actual: int) -> float:
    """Brier score de un partido."""
    total = 0.0
    for i in range(3):
        target = 1.0 if i == actual else 0.0
        total += (probs[i] - target) ** 2
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--last-n", type=int)
    parser.add_argument("--output", help="Guardar resultados a JSON")
    args = parser.parse_args()

    DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Obtener fixtures
    if args.last_n:
        query = """
            SELECT id, season_id, home_team_id, away_team_id, starting_at,
                   home_score, away_score
            FROM fixtures
            WHERE league_id = 743
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
            ORDER BY starting_at DESC
            LIMIT ?
        """
        fixtures = conn.execute(query, (args.last_n,)).fetchall()
        fixtures = list(reversed(fixtures))
    else:
        query = """
            SELECT id, season_id, home_team_id, away_team_id, starting_at,
                   home_score, away_score
            FROM fixtures
            WHERE league_id = 743
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
              AND starting_at >= ?
              AND starting_at < ?
            ORDER BY starting_at
        """
        fixtures = conn.execute(query, (args.start, args.end)).fetchall()

    print(f"📊 {len(fixtures)} fixtures en rango")

    # Pre-cargar narrativas
    print("⏳ Cargando narrativas...")
    narratives_cache = {}
    season_ids = set(f['season_id'] for f in fixtures)
    for sid in season_ids:
        season_name = conn.execute("SELECT name FROM seasons WHERE id = ?", (sid,)).fetchone()
        if season_name:
            narratives_cache[sid] = load_manual_narratives(season_name['name'].split('/')[0].strip())
        else:
            narratives_cache[sid] = load_manual_narratives()

    # Acumular stats por equipo
    team_stats = {}  # team_id → {as_home: [], as_away: []}

    print("⏳ Corriendo predicciones por equipo...")
    for i, f in enumerate(fixtures):
        if i % 50 == 0:
            print(f"  Progreso: {i}/{len(fixtures)}...")

        season_id = f['season_id']
        try:
            pred = predict_match(
                conn,
                home_id=f['home_team_id'],
                away_id=f['away_team_id'],
                season_id=season_id,
                fixture_date=str(f['starting_at']),
                narratives=narratives_cache[season_id],
            )
            if pred is None:
                continue
            ensemble = pred['ensemble']
            probs = [ensemble['home'], ensemble['draw'], ensemble['away']]
            actual = get_actual_result(f['home_score'], f['away_score'])
            brier = brier_per_match(probs, actual)
            hit = 1 if probs.index(max(probs)) == actual else 0

            # Acumular por equipo
            home_id = f['home_team_id']
            away_id = f['away_team_id']

            for team_id, role in [(home_id, "home"), (away_id, "away")]:
                if team_id not in team_stats:
                    team_stats[team_id] = []
                team_stats[team_id].append({
                    "role": role,
                    "probs": probs,
                    "actual": actual,
                    "hit": hit,
                    "brier": brier,
                    "fixture_id": f['id'],
                })
        except Exception:
            continue

    # Calcular métricas por equipo
    print("\n📊 Calculando métricas por equipo...")
    team_metrics = []
    for team_id, matches in team_stats.items():
        if len(matches) < 5:
            continue

        # Accuracy y Brier
        n = len(matches)
        accuracy = sum(m['hit'] for m in matches) / n
        avg_brier = sum(m['brier'] for m in matches) / n

        # Accuracy como local y visitante
        home_matches = [m for m in matches if m['role'] == 'home']
        away_matches = [m for m in matches if m['role'] == 'away']

        home_acc = sum(m['hit'] for m in home_matches) / len(home_matches) if home_matches else None
        away_acc = sum(m['hit'] for m in away_matches) / len(away_matches) if away_matches else None

        # Nombre del equipo
        team_name = conn.execute("SELECT name FROM teams WHERE id = ?", (team_id,)).fetchone()
        team_name_str = team_name['name'] if team_name else f"#{team_id}"

        team_metrics.append({
            "team_id": team_id,
            "team": team_name_str,
            "n_matches": n,
            "n_home": len(home_matches),
            "n_away": len(away_matches),
            "accuracy": round(accuracy, 4),
            "brier": round(avg_brier, 4),
            "accuracy_home": round(home_acc, 4) if home_acc is not None else None,
            "accuracy_away": round(away_acc, 4) if away_acc is not None else None,
        })

    # Ordenar por accuracy
    team_metrics.sort(key=lambda x: x['accuracy'], reverse=True)

    # Imprimir tabla
    print("\n" + "=" * 90)
    print("📊 ACCURACY POR EQUIPO")
    print("=" * 90)
    print(f"{'Equipo':<25} {'N':>4} {'Local':>7} {'Visit':>7} {'Total':>8} {'Brier':>8}")
    print("-" * 90)

    for tm in team_metrics:
        home_str = f"{tm['accuracy_home']:.0%}" if tm['accuracy_home'] is not None else "N/A"
        away_str = f"{tm['accuracy_away']:.0%}" if tm['accuracy_away'] is not None else "N/A"
        print(f"{tm['team']:<25} {tm['n_matches']:>4} {home_str:>7} {away_str:>7} "
              f"{tm['accuracy']:>7.2%} {tm['brier']:>8.4f}")

    print()
    print("=" * 90)
    print("🏆 TOP 5 (mejor accuracy):")
    print("-" * 90)
    for tm in team_metrics[:5]:
        print(f"  ✅ {tm['team']:<25} {tm['accuracy']:>6.2%} ({tm['n_matches']} partidos, "
              f"Brier {tm['brier']:.3f})")

    print()
    print("⚠️ BOTTOM 5 (peor accuracy):")
    print("-" * 90)
    for tm in team_metrics[-5:]:
        print(f"  ❌ {tm['team']:<25} {tm['accuracy']:>6.2%} ({tm['n_matches']} partidos, "
              f"Brier {tm['brier']:.3f})")

    # Guardar
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "config": {
                    "start": args.start,
                    "end": args.end,
                },
                "team_metrics": team_metrics,
            }, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Resultados guardados en {output_path}")

    conn.close()


if __name__ == "__main__":
    main()