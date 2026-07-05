"""
backtest_xg.py — Backtest comparativo CON/SIN xG rolling.

Compara:
  1. Baseline (Elo 55% + DC 30% + heur 15%)  [status quo]
  2. Con xG: Elo 50% + DC 25% + heur 10% + xG 15%
  3. Con xG: Elo 45% + DC 25% + heur 10% + xG 20%
  4. Con xG: Elo 40% + DC 25% + heur 10% + xG 25%

Reporta accuracy, Brier, log loss, calibration.

Uso:
  python3 src/predict/backtest_xg.py --start 2024-01-01 --end 2025-12-31
"""

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.backtest import predict_match
from predict.xg import get_xg_1x2_prediction, precompute_xg_lookup


# Métricas --------------------------------------------------------------------

def brier(probs: List[float], actual: int) -> float:
    return sum((p - (1.0 if i == actual else 0.0)) ** 2 for i, p in enumerate(probs))


def nll(probs: List[float], actual: int) -> float:
    p = max(probs[actual], 1e-9)
    return -math.log(p)


def to_list(p: Dict[str, float]) -> List[float]:
    return [p.get('home', p.get('home_win', 0)), p.get('draw', 0), p.get('away', p.get('away_win', 0))]


def get_actual(hs: int, as_: int) -> int:
    if hs > as_: return 0
    if hs < as_: return 2
    return 1


def metrics(results: List[Dict], probs_key: str = 'probs') -> Dict[str, float]:
    n = len(results)
    if n == 0:
        return {'n': 0, 'acc': 0, 'brier': 0, 'nll': 0}
    hits = sum(1 for r in results if r[probs_key].index(max(r[probs_key])) == r['actual'])
    brier_sum = sum(brier(r[probs_key], r['actual']) for r in results)
    nll_sum = sum(nll(r[probs_key], r['actual']) for r in results)
    return {
        'n': n,
        'acc': hits / n,
        'brier': brier_sum / n,
        'nll': nll_sum / n,
    }


# Configuraciones del ensemble ------------------------------------------------

ENSEMBLE_CONFIGS = []
# Grid search fino alrededor del óptimo
for xg_w in [0.45, 0.50, 0.52, 0.55, 0.58, 0.60, 0.62, 0.65]:
    elo_w = (1.0 - xg_w) * 0.5
    dc_w = (1.0 - xg_w) * 0.3
    heur_w = (1.0 - xg_w) * 0.2
    ENSEMBLE_CONFIGS.append({
        'name': f'xg={xg_w:.0%}',
        'weights': {'elo': round(elo_w, 3), 'dc': round(dc_w, 3), 'heur': round(heur_w, 3), 'xg': xg_w},
    })
# Agregar el baseline como referencia
ENSEMBLE_CONFIGS.insert(0, {
    'name': 'baseline (Elo 55 + DC 30 + heur 15)',
    'weights': {'elo': 0.55, 'dc': 0.30, 'heur': 0.15, 'xg': 0.00},
})
ENSEMBLE_CONFIGS.append({
    'name': 'xg_only (xG 100)',
    'weights': {'elo': 0.00, 'dc': 0.00, 'heur': 0.00, 'xg': 1.00},
})


def build_ensemble(p_elo: List[float], p_dc: List[float], p_h: List[float], p_xg: List[float], weights: Dict[str, float]) -> List[float]:
    out = [
        weights['elo'] * p_elo[i] + weights['dc'] * p_dc[i] + weights['heur'] * p_h[i] + weights['xg'] * p_xg[i]
        for i in range(3)
    ]
    s = sum(out)
    return [x / s for x in out]
    out = [
        weights['elo'] * p_elo[i] + weights['dc'] * p_dc[i] + weights['heur'] * p_h[i] + weights['xg'] * p_xg[i]
        for i in range(3)
    ]
    s = sum(out)
    return [x / s for x in out]


# Backtest --------------------------------------------------------------------

def run_backtest(
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    league_id: int = 743,
) -> Dict[str, Any]:
    print(f"📊 BACKTEST CON/SIN xG: {start_date} → {end_date}")
    print("=" * 70)

    conn = sqlite3.connect(str(PROJECT_ROOT / "data" / "predictions_mx.db"))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT f.id, f.home_team_id, f.away_team_id, f.home_score, f.away_score,
               f.starting_at, f.season_id
        FROM fixtures f
        WHERE f.league_id = ?
          AND f.home_score IS NOT NULL
          AND date(f.starting_at) BETWEEN ? AND ?
        ORDER BY f.starting_at
    """, (league_id, start_date, end_date)).fetchall()

    print(f"Total partidos: {len(rows)}\n")

    # Precomputar xG cache
    print("Precomputando xG rolling...")
    import time
    t0 = time.time()
    xg_cache = precompute_xg_lookup(conn)
    print(f"Cache listo en {time.time()-t0:.2f}s "
          f"({len(xg_cache['attack'])} equipos, {len(xg_cache['dates'])} fechas)\n")

    # Almacenar predicciones crudas (por partido)
    raw_preds = []  # lista de dicts con probs de cada modelo

    narratives = {'narratives': [], 'derbies': []}
    errors = 0

    for row in rows:
        fid, h, a, hs, as_, date, season_id = row
        try:
            pred = predict_match(conn, h, a, season_id, date, narratives)
            if pred is None:
                continue
            xg_pred = get_xg_1x2_prediction(conn, h, a, before_date=date, _cache=xg_cache)
            if not isinstance(xg_pred, dict) or 'home_win' not in xg_pred:
                errors += 1
                if errors < 3:
                    print(f"⚠️  xg_pred malformado en {fid}: type={type(xg_pred)} keys={list(xg_pred.keys()) if isinstance(xg_pred, dict) else 'N/A'}")
                continue
            actual = get_actual(hs, as_)

            raw_preds.append({
                'fixture_id': fid,
                'home_id': h, 'away_id': a,
                'home_score': hs, 'away_score': as_,
                'date': date,
                'actual': actual,
                'dc': to_list(pred['dc']),
                'elo': to_list(pred['elo']),
                'heuristic': to_list(pred['heuristic']),
                'xg': [xg_pred['home_win'], xg_pred['draw'], xg_pred['away_win']],
            })
        except Exception as e:
            errors += 1
            if errors < 3:
                import traceback
                print(f"⚠️  Error en fixture {fid}: {e}")
                traceback.print_exc()

    if errors:
        print(f"⚠️  {errors} errores omitidos\n")

    print(f"Predicciones exitosas: {len(raw_preds)}\n")

    # Calcular métricas para cada config
    summary = {'total': len(raw_preds), 'configs': {}}
    for cfg in ENSEMBLE_CONFIGS:
        # Calcular ensemble
        for r in raw_preds:
            r['ensemble'] = build_ensemble(r['elo'], r['dc'], r['heuristic'], r['xg'], cfg['weights'])
            r['probs'] = r['ensemble']  # para que metrics() use ensemble
        m = metrics(raw_preds, 'probs')
        summary['configs'][cfg['name']] = {
            'weights': cfg['weights'],
            **m,
        }

    # También métricas individuales por modelo
    for model_name in ['elo', 'dc', 'heuristic', 'xg']:
        for r in raw_preds:
            r['probs'] = r[model_name]
        m = metrics(raw_preds, 'probs')
        summary[f'model_{model_name}'] = m

    return summary


def print_summary(summary: Dict[str, Any]) -> None:
    print(f"\n📈 RESULTADOS (n={summary['total']})")
    print("=" * 90)
    print(f"{'Config':50s} {'Acc':>6s} {'Brier':>7s} {'NLL':>7s}")
    print("-" * 90)

    # Modelos individuales
    print("--- Modelos individuales ---")
    for k in ['model_elo', 'model_dc', 'model_heuristic', 'model_xg']:
        m = summary[k]
        if m['n'] > 0:
            print(f"  {k:48s} {m['acc']*100:5.2f}% {m['brier']:.4f}  {m['nll']:.4f}")
    print()

    # Ensembles
    print("--- Ensembles ---")
    for name, m in summary['configs'].items():
        print(f"  {name:48s} {m['acc']*100:5.2f}% {m['brier']:.4f}  {m['nll']:.4f}")
    print()

    # Mejor
    best = max(summary['configs'].items(), key=lambda x: x[1]['acc'])
    base = summary['configs']['baseline (Elo 55 + DC 30 + heur 15)']
    delta_acc = (best[1]['acc'] - base['acc']) * 100
    delta_brier = best[1]['brier'] - base['brier']
    print(f"🏆 Mejor: {best[0]}")
    print(f"   vs baseline: Δ acc = {delta_acc:+.2f}pp, Δ brier = {delta_brier:+.4f}")


# CLI -------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2024-01-01')
    parser.add_argument('--end', default='2025-12-31')
    args = parser.parse_args()
    summary = run_backtest(args.start, args.end)
    print_summary(summary)


if __name__ == '__main__':
    main()
