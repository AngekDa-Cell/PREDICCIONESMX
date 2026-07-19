#!/usr/bin/env python3
"""
build_calibration_dataset.py — Genera dataset de (probs, outcome) para calibración.

Para cada partido finalizado en Liga MX, llama a predict_match() y guarda:
  - fixture_id, season, match_date, home_team, away_team
  - probs: home_win, draw, away_win (ensemble + sub-modelos)
  - actual: 'home'/'away'/'draw' (basado en scores reales)

Output: CSV en /workspace/proyectos/data/calibration_dataset.csv

Uso:
  python3 scripts/build_calibration_dataset.py              # todas las temporadas
  python3 scripts/build_calibration_dataset.py --last-n 600 # últimos N partidos
  python3 scripts/build_calibration_dataset.py --start 2024-07-01 --end 2025-06-30
"""

import sys
import csv
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
LEAGUE_ID = 743
OUTPUT_PATH = PROJECT_ROOT / "data" / "calibration_dataset.csv"

CSV_COLUMNS = [
    "fixture_id", "season", "match_date", "home_team", "away_team",
    "actual", "home_score", "away_score",
    "ens_home", "ens_draw", "ens_away",
    "xg_home", "xg_draw", "xg_away",
    "elo_home", "elo_draw", "elo_away",
    "dc_home", "dc_draw", "dc_away",
    "heur_home", "heur_draw", "heur_away",
]


def fetch_finished_fixtures(conn, last_n=None, start=None, end=None):
    """Devuelve los partidos finalizados que vamos a procesar."""
    query = """
        SELECT f.id, s.name AS season, f.starting_at,
               t1.name AS home_team, t2.name AS away_team,
               f.home_team_id, f.away_team_id, f.season_id,
               f.home_score, f.away_score
        FROM fixtures f
        JOIN seasons s ON s.id = f.season_id
        JOIN teams t1 ON t1.id = f.home_team_id
        JOIN teams t2 ON t2.id = f.away_team_id
        WHERE f.league_id = ?
          AND f.home_score IS NOT NULL
          AND f.away_score IS NOT NULL
    """
    params = [LEAGUE_ID]
    if start:
        query += " AND f.starting_at >= ?"
        params.append(start)
    if end:
        query += " AND f.starting_at < ?"
        params.append(end)
    query += " ORDER BY f.starting_at"
    if last_n:
        query = f"""
            SELECT * FROM ({query}) ORDER BY starting_at DESC LIMIT ?
        """
        params.append(last_n)
        query = f"SELECT * FROM ({query}) ORDER BY starting_at"
    return query, params


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--last-n", type=int, help="Solo últimos N partidos finalizados")
    parser.add_argument("--start", help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end", help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()

    print(f"🔨 BUILD CALIBRATION DATASET")
    print(f"   {datetime.now().isoformat()}")
    if args.last_n:
        print(f"   last_n={args.last_n}")
    if args.start or args.end:
        print(f"   range: {args.start} → {args.end}")

    conn = sqlite3.connect(str(DB_PATH))
    query, params = fetch_finished_fixtures(conn, args.last_n, args.start, args.end)
    rows = conn.execute(query, params).fetchall()
    print(f"\n📋 {len(rows)} partidos a procesar")
    print(f"   Esperado ~5-15 min según n...\n")

    # Importar módulos
    from predict.backtest import predict_match
    from predict import xg as xg_mod
    from predict.xg import precompute_xg_lookup, get_xg_1x2_prediction as _orig_get_xg

    # Precomputar cache xG (performance)
    import time
    t0 = time.time()
    xg_cache = precompute_xg_lookup(conn)
    print(f"xG cache: {len(xg_cache['attack'])} equipos ({time.time()-t0:.1f}s)\n")

    def _get_xg_cached(conn_, h_, a_, before_date=None, **_):
        return _orig_get_xg(conn_, h_, a_, before_date=before_date, _cache=xg_cache)
    xg_mod.get_xg_1x2_prediction = _get_xg_cached
    sys.modules['predict.xg'].get_xg_1x2_prediction = _get_xg_cached

    # Procesar
    results = []
    errors = 0
    t0 = time.time()

    for i, (fid, season, date, home, away, h_id, a_id, s_id, hs, as_) in enumerate(rows):
        if (i + 1) % 25 == 0 or i == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(rows) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(rows)}] {home:20s} vs {away:20s} | elapsed={elapsed:.0f}s ETA={eta:.0f}s")

        actual = "home" if hs > as_ else ("away" if as_ > hs else "draw")
        try:
            narratives = {"narratives": [], "derbies": []}
            pred = predict_match(conn, h_id, a_id, s_id, date, narratives)
            if pred is None or "ensemble" not in pred:
                errors += 1
                continue
            ens = pred["ensemble"]
            results.append({
                "fixture_id": fid,
                "season": season,
                "match_date": date,
                "home_team": home,
                "away_team": away,
                "actual": actual,
                "home_score": hs,
                "away_score": as_,
                "ens_home": ens["home"], "ens_draw": ens["draw"], "ens_away": ens["away"],
                "xg_home": pred["xg"]["home"], "xg_draw": pred["xg"]["draw"], "xg_away": pred["xg"]["away"],
                "elo_home": pred["elo"]["home"], "elo_draw": pred["elo"]["draw"], "elo_away": pred["elo"]["away"],
                "dc_home": pred["dc"]["home"], "dc_draw": pred["dc"]["draw"], "dc_away": pred["dc"]["away"],
                "heur_home": pred["heuristic"]["home"], "heur_draw": pred["heuristic"]["draw"],
                "heur_away": pred["heuristic"]["away"],
            })
        except Exception as e:
            errors += 1
            continue

    # Escribir CSV
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(results)

    elapsed = time.time() - t0
    print(f"\n✅ Guardados {len(results)} partidos en {args.output}")
    print(f"   Errores: {errors}")
    print(f"   Tiempo total: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print()
    print("Sig. paso: ajustar Platt scaling con:")
    print(f"   python3 scripts/fit_platt_scaling.py --input {args.output}")


if __name__ == "__main__":
    main()
