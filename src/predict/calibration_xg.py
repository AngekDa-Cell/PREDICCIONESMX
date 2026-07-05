"""
calibration_xg.py — Calibración del ensemble CON xG.

Mide la calibración (predicted vs actual) por bucket de probabilidad.
"""
import sys
import json
import sqlite3
import math
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.backtest import predict_match
from predict.xg import get_xg_1x2_prediction, precompute_xg_lookup


def build_ensemble(p_elo, p_dc, p_h, p_xg, weights):
    out = [weights['elo']*p_elo[i] + weights['dc']*p_dc[i] + weights['heur']*p_h[i] + weights['xg']*p_xg[i] for i in range(3)]
    s = sum(out)
    return [x/s for x in out]


def get_actual(hs, as_):
    if hs > as_: return 0
    if hs < as_: return 2
    return 1


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2024-01-01')
    parser.add_argument('--end', default='2025-12-31')
    parser.add_argument('--xg-weight', type=float, default=0.55)
    args = parser.parse_args()

    xg_w = args.xg_weight
    elo_w = (1 - xg_w) * 0.5
    dc_w = (1 - xg_w) * 0.3
    heur_w = (1 - xg_w) * 0.2

    print(f"📊 CALIBRACIÓN: xg={xg_w}, elo={elo_w:.3f}, dc={dc_w:.3f}, heur={heur_w:.3f}")
    print(f"   Rango: {args.start} → {args.end}\n")

    conn = sqlite3.connect(str(PROJECT_ROOT / "data" / "predictions_mx.db"))
    conn.row_factory = sqlite3.Row

    cache = precompute_xg_lookup(conn)
    print(f"Cache xG: {len(cache['attack'])} equipos\n")

    rows = conn.execute("""
        SELECT f.id, f.home_team_id, f.away_team_id, f.home_score, f.away_score,
               f.starting_at, f.season_id
        FROM fixtures f
        WHERE f.league_id = 743
          AND f.home_score IS NOT NULL
          AND date(f.starting_at) BETWEEN ? AND ?
        ORDER BY f.starting_at
    """, (args.start, args.end)).fetchall()

    narratives = {'narratives': [], 'derbies': []}
    results = []

    for row in rows:
        fid, h, a, hs, as_, date, season_id = row
        try:
            pred = predict_match(conn, h, a, season_id, date, narratives)
            if pred is None: continue
            xg = get_xg_1x2_prediction(conn, h, a, before_date=date, _cache=cache)
            actual = get_actual(hs, as_)
            p_ens = build_ensemble(
                [pred['elo']['home'], pred['elo']['draw'], pred['elo']['away']],
                [pred['dc']['home'], pred['dc']['draw'], pred['dc']['away']],
                [pred['heuristic']['home'], pred['heuristic']['draw'], pred['heuristic']['away']],
                [xg['home_win'], xg['draw'], xg['away_win']],
                {'elo': elo_w, 'dc': dc_w, 'heur': heur_w, 'xg': xg_w},
            )
            results.append({
                'home_id': h, 'away_id': a,
                'home_score': hs, 'away_score': as_,
                'probs': p_ens,
                'actual': actual,
            })
        except Exception as e:
            pass

    print(f"Partidos procesados: {len(results)}\n")

    # Calibración por bucket de P(home)
    print("📈 CALIBRACIÓN (P(home)):")
    print(f"{'Predicted':>10s} {'N':>6s} {'Actual':>8s} {'Delta':>8s}")
    print("-" * 40)
    for prob_target in [0.30, 0.40, 0.50, 0.60, 0.70, 0.80]:
        bucket = [r for r in results if abs(r['probs'][0] - prob_target) < 0.07]
        if len(bucket) < 5: continue
        actual_home = sum(1 for r in bucket if r['actual'] == 0) / len(bucket)
        print(f"{prob_target:>10.2f} {len(bucket):>6d} {actual_home:>8.3f} {actual_home-prob_target:>+8.3f}")

    # Calibración por bucket de max prob (la predicha)
    print("\n📈 CALIBRACIÓN (max prob, la elección del modelo):")
    print(f"{'Predicted':>10s} {'N':>6s} {'Hit%':>8s} {'Delta':>8s}")
    print("-" * 40)
    for prob_target in [0.40, 0.50, 0.60, 0.70, 0.80, 0.90]:
        bucket = [r for r in results if abs(max(r['probs']) - prob_target) < 0.07]
        if len(bucket) < 5: continue
        hits = sum(1 for r in bucket if r['probs'].index(max(r['probs'])) == r['actual'])
        hit_rate = hits / len(bucket)
        print(f"{prob_target:>10.2f} {len(bucket):>6d} {hit_rate:>8.3f} {hit_rate-prob_target:>+8.3f}")


if __name__ == '__main__':
    main()
