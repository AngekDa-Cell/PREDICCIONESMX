"""
grid_search_heur_weight.py — Grid search del peso de heur en el ensemble.

Prueba varios valores de heuristic_weight (manteniendo proporciones xG:elo:dc:heur)
y mide accuracy + Brier en backtest 2024-2025.

Nota: Como los modelos son pesados, hace UNA pasada del backtest y re-pondera
los outputs cached por partido.
"""
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.backtest import run_backtest


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2024-01-01')
    parser.add_argument('--end', default='2025-12-31')
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))

    # Run backtest UNA VEZ con pesos default (captura las predicciones de cada modelo)
    print("Running base backtest (1 pasada)...")
    summary = run_backtest(conn, args.start, args.end)

    # Como el summary solo guarda accuracy por modelo, no las predicciones individuales,
    # re-corro los partidos y guardo las probs individuales en memoria.
    # Esto lo hacemos modificando run_backtest temporalmente.

    # Estrategia alternativa: directamente itero sobre cada partido y guardo probs.
    print("Running detailed backtest (cachea probs por partido)...")
    from predict.features import get_full_feature_set
    from predict.dixon_coles import fit_dixon_coles, predict_from_model
    from predict.elo import get_elo_predictions
    from predict.xg import get_xg_1x2_prediction, precompute_xg_lookup
    from predict.heuristics import apply_heuristics, load_manual_narratives
    from predict.misc_utils import get_shrinkage_factor

    # Precompute xG lookup
    xg_lookup = precompute_xg_lookup(conn)

    fixtures = conn.execute("""
        SELECT id, home_team_id, away_team_id, season_id, starting_at
        FROM fixtures
        WHERE league_id=743
          AND starting_at BETWEEN ? AND ?
          AND home_score IS NOT NULL
        ORDER BY starting_at
    """, (args.start, args.end)).fetchall()
    print(f"Fixtures a procesar: {len(fixtures)}")

    # Cachear season_id → modelo DC
    seasons_to_fit = set(f[3] for f in fixtures)
    dc_models = {}
    for sid in seasons_to_fit:
        m = fit_dixon_coles(conn, sid)
        if m:
            dc_models[sid] = m

    narratives = load_manual_narratives()

    # Cachear probs de cada modelo por partido
    cached = []
    team_shrink_path = PROJECT_ROOT / "data" / "team_local_shrinkage.json"
    team_shrinkages = {}
    if team_shrink_path.exists():
        with open(team_shrink_path) as f:
            team_shrinkages = json.load(f).get("teams", {})

    shrinkage = get_shrinkage_factor()

    coefs = json.load(open(PROJECT_ROOT / "src" / "predict" / "mx_coefficients.json"))

    n_done = 0
    for fid, h, a, sid, fdate in fixtures:
        if sid not in dc_models:
            continue
        try:
            features = get_full_feature_set(conn, h, a, sid, fdate)
            features['home_team_name'] = conn.execute("SELECT name FROM teams WHERE id=?", (h,)).fetchone()[0]
            features['away_team_name'] = conn.execute("SELECT name FROM teams WHERE id=?", (a,)).fetchone()[0]

            home_alt = features['altitude'].get('home_altitude', 0) or 0
            away_alt = features['altitude'].get('away_altitude', 0) or 0
            rest_diff = features['rest'].get('rest_diff', 0)
            form_diff = features['home_form'].get('momentum', 0) - features['away_form'].get('momentum', 0)
            h2h_rate = features['h2h'].get('a_win_rate', 0.5)

            dc_o = predict_from_model(dc_models[sid], h, a, home_alt, away_alt, rest_diff, form_diff, h2h_rate)
            elo_o = get_elo_predictions(conn, h, a, before_date=fdate, shrinkage_factor=shrinkage, team_shrinkages=team_shrinkages)
            adj_o = apply_heuristics(features, narratives, dc_o)
            xg_o = get_xg_1x2_prediction(conn, h, a, before_date=fdate, lookup=xg_lookup)

            row = conn.execute("SELECT home_score, away_score FROM fixtures WHERE id=?", (fid,)).fetchone()
            actual = 'home' if row[0] > row[1] else ('draw' if row[0] == row[1] else 'away')

            cached.append({
                'fixture_id': fid,
                'actual': actual,
                'dc': dc_o,
                'elo': elo_o,
                'heuristic': adj_o,
                'xg': xg_o,
                'confidence': adj_o.get('confidence', 0.5),
            })
        except Exception as ex:
            pass

        n_done += 1
        if n_done % 100 == 0:
            print(f"  {n_done}/{len(fixtures)} done...")

    print(f"Cacheado: {len(cached)} partidos\n")

    # Grid search
    weights_to_try = [
        (0.55, 0.225, 0.135, 0.09),   # baseline
        (0.50, 0.225, 0.135, 0.14),   # +5pp heur
        (0.45, 0.225, 0.135, 0.19),   # +10pp heur
        (0.40, 0.225, 0.135, 0.24),   # +15pp heur
        (0.50, 0.20, 0.13, 0.17),
        (0.45, 0.20, 0.13, 0.22),
    ]

    def brier(probs, actual):
        actual_idx = {'home': 0, 'draw': 1, 'away': 2}[actual]
        return sum((p - (1 if i == actual_idx else 0)) ** 2 for i, p in enumerate(probs))

    def eval_weights(idx):
        hits = 0
        total_brier = 0
        xg_w, elo_w, dc_w, heur_w = weights_to_try[idx]
        for r in cached:
            probs = [
                r['xg']['home_win'] * xg_w + r['elo']['home_win'] * elo_w + r['dc']['home_win'] * dc_w + r['heuristic']['home_win'] * heur_w,
                r['xg']['draw'] * xg_w + r['elo']['draw'] * elo_w + r['dc']['draw'] * dc_w + r['heuristic']['draw'] * heur_w,
                r['xg']['away_win'] * xg_w + r['elo']['away_win'] * elo_w + r['dc']['away_win'] * dc_w + r['heuristic']['away_win'] * heur_w,
            ]
            # Normalizar
            tot = sum(probs)
            probs = [p / tot for p in probs]
            pred = probs.index(max(probs))
            pred_lbl = ['home', 'draw', 'away'][pred]
            if pred_lbl == r['actual']:
                hits += 1
            total_brier += brier(probs, r['actual'])

        return {
            'accuracy': hits / len(cached) * 100,
            'brier': total_brier / len(cached),
        }

    print("=" * 70)
    print("GRID SEARCH DE PESOS HEURÍSTICOS")
    print("=" * 70)
    print(f"{'xg':<6} {'elo':<6} {'dc':<6} {'heur':<6} {'acc':<8} {'brier':<8} {'Δacc':<8} {'Δbrier':<8}")
    print("-" * 70)

    baseline_acc = None
    baseline_brier = None
    best = None
    best_acc = 0

    for i, w in enumerate(weights_to_try):
        r = eval_weights(i)
        if baseline_acc is None:
            baseline_acc = r['accuracy']
            baseline_brier = r['brier']

        d_acc = r['accuracy'] - baseline_acc
        d_brier = r['brier'] - baseline_brier

        marker = " ← MEJOR" if r['accuracy'] > best_acc else ""
        if r['accuracy'] > best_acc:
            best_acc = r['accuracy']
            best = (w, r)

        print(f"{w[0]:<6.3f} {w[1]:<6.3f} {w[2]:<6.3f} {w[3]:<6.3f} {r['accuracy']:<8.2f} {r['brier']:<8.4f} {d_acc:<+8.2f} {d_brier:<+8.4f}{marker}")

    print()
    if best:
        w, r = best
        print(f"🏆 Mejor: {w} → acc={r['accuracy']:.2f}%, brier={r['brier']:.4f}")
        if r['accuracy'] > baseline_acc:
            print(f"   Δ vs baseline: +{r['accuracy'] - baseline_acc:.2f}pp accuracy, {r['brier'] - baseline_brier:+.4f} brier")
            print(f"   ⚡ RECOMENDACIÓN: actualizar mx_coefficients.json con nuevos pesos")
        else:
            print(f"   ❌ Ningún peso mejora sobre baseline (9% heur)")

    # Guardar resultados
    out_path = PROJECT_ROOT / "data" / "grid_search_heur.json"
    with open(out_path, "w") as f:
        json.dump({
            "range": f"{args.start} → {args.end}",
            "n_matches": len(cached),
            "weights_tested": [
                {
                    "xg": w[0], "elo": w[1], "dc": w[2], "heur": w[3],
                    "accuracy": eval_weights(i)['accuracy'],
                    "brier": eval_weights(i)['brier'],
                }
                for i, w in enumerate(weights_to_try)
            ],
            "best": {"weights": best[0], "result": best[1]} if best else None,
        }, f, indent=2)
    print(f"\n  Guardado en: data/grid_search_heur.json")


if __name__ == "__main__":
    main()