"""
stacking_walkforward.py — Walk-forward validation del stacking.

Simula uso en producción: en cada ventana temporal, entrena con datos hasta T
y predice para T+1. Mide accuracy y Brier en cada fold.

Esto es la validación más realista — el modelo nunca ve el futuro.
"""
import sys
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np
from predict.stacking import cache_predictions, to_xy, train_meta_learner, evaluate


def walk_forward_eval(
    conn: sqlite3.Connection,
    windows: List[Tuple[str, str, str, str]],
    model_type: str = 'xgb',
) -> Dict:
    """Evalúa el modelo con walk-forward en cada window.

    Args:
        windows: lista de (train_start, train_end, test_start, test_end)

    Returns:
        Dict con métricas por fold y agregado
    """
    results = []

    for i, (ts, te, vs, ve) in enumerate(windows):
        print(f"\n=== Fold {i+1}/{len(windows)} ===")
        print(f"   Train: {ts} → {te}")
        print(f"   Test:  {vs} → {ve}")

        train_data = cache_predictions(conn, ts, te)
        test_data = cache_predictions(conn, vs, ve)

        if len(train_data) < 50 or len(test_data) < 10:
            print(f"   ⚠️  Datos insuficientes, saltando")
            continue

        X_train, y_train = to_xy(train_data)
        X_test, y_test = to_xy(test_data)

        model = train_meta_learner(X_train, y_train, model_type=model_type)

        # Evaluar train (overfitting check)
        train_probs = model.predict_proba(X_train)
        train_metrics = evaluate(train_probs, y_train)

        # Evaluar test
        test_probs = model.predict_proba(X_test)
        test_metrics = evaluate(test_probs, y_test)

        # Evaluar baseline ensemble
        baseline_probs = np.zeros((len(test_data), 3))
        for j, r in enumerate(test_data):
            baseline_probs[j, 0] = (
                r['xg_home'] * 0.55 + r['elo_home'] * 0.225 +
                r['dc_home'] * 0.135 + r['heur_home'] * 0.09
            )
            baseline_probs[j, 1] = (
                r['xg_draw'] * 0.55 + r['elo_draw'] * 0.225 +
                r['dc_draw'] * 0.135 + r['heur_draw'] * 0.09
            )
            baseline_probs[j, 2] = (
                r['xg_away'] * 0.55 + r['elo_away'] * 0.225 +
                r['dc_away'] * 0.135 + r['heur_away'] * 0.09
            )
        baseline_probs = baseline_probs / baseline_probs.sum(axis=1, keepdims=True)
        baseline_metrics = evaluate(baseline_probs, y_test)

        delta_acc = test_metrics['accuracy'] - baseline_metrics['accuracy']
        delta_brier = test_metrics['brier'] - baseline_metrics['brier']

        fold_result = {
            'fold': i + 1,
            'train': [ts, te],
            'test': [vs, ve],
            'n_train': len(train_data),
            'n_test': len(test_data),
            'train_metrics': train_metrics,
            'test_metrics': test_metrics,
            'baseline': baseline_metrics,
            'delta_acc_pp': round(delta_acc, 2),
            'delta_brier': round(delta_brier, 4),
        }
        results.append(fold_result)

        print(f"   Baseline: acc={baseline_metrics['accuracy']:.2f}% brier={baseline_metrics['brier']:.4f}")
        print(f"   Stacking: acc={test_metrics['accuracy']:.2f}% brier={test_metrics['brier']:.4f}")
        print(f"   Δ: acc={delta_acc:+.2f}pp brier={delta_brier:+.4f}")

    # Aggregate
    if results:
        agg = {
            'n_folds': len(results),
            'mean_baseline_acc': np.mean([r['baseline']['accuracy'] for r in results]),
            'mean_stacking_acc': np.mean([r['test_metrics']['accuracy'] for r in results]),
            'mean_baseline_brier': np.mean([r['baseline']['brier'] for r in results]),
            'mean_stacking_brier': np.mean([r['test_metrics']['brier'] for r in results]),
            'mean_delta_acc': np.mean([r['delta_acc_pp'] for r in results]),
            'mean_delta_brier': np.mean([r['delta_brier'] for r in results]),
            'folds_improved_acc': sum(1 for r in results if r['delta_acc_pp'] > 0),
            'folds_improved_brier': sum(1 for r in results if r['delta_brier'] < -0.005),
        }

        print("\n" + "=" * 70)
        print("📊 AGREGADO WALK-FORWARD")
        print("=" * 70)
        print(f"  Folds: {agg['n_folds']}")
        print(f"  Baseline acc:    {agg['mean_baseline_acc']:.2f}%")
        print(f"  Stacking acc:    {agg['mean_stacking_acc']:.2f}%")
        print(f"  Δ accuracy:      {agg['mean_delta_acc']:+.2f}pp")
        print()
        print(f"  Baseline Brier:  {agg['mean_baseline_brier']:.4f}")
        print(f"  Stacking Brier:  {agg['mean_stacking_brier']:.4f}")
        print(f"  Δ Brier:         {agg['mean_delta_brier']:+.4f}")
        print()
        print(f"  Folds con acc mejor:    {agg['folds_improved_acc']}/{agg['n_folds']}")
        print(f"  Folds con Brier mejor:  {agg['folds_improved_brier']}/{agg['n_folds']}")

        return {'folds': results, 'aggregate': agg}
    return {'folds': results}


def main():
    # 5 ventanas walk-forward:
    # Cada ventana: train con ~6 meses, test con los siguientes 2-3 meses
    windows = [
        # Train 2023 H2, test 2024 H1
        ('2023-07-01', '2023-12-31', '2024-01-01', '2024-06-30'),
        # Train 2023 H2 → 2024 H1, test 2024 H2
        ('2023-07-01', '2024-06-30', '2024-07-01', '2024-12-31'),
        # Train 2024, test 2025 H1
        ('2024-01-01', '2024-12-31', '2025-01-01', '2025-06-30'),
        # Train 2023-2024, test 2025 completo
        ('2023-07-01', '2024-12-31', '2025-01-01', '2025-12-31'),
        # Train 2023-2024 + 2025 H1, test 2025 H2
        ('2023-07-01', '2025-06-30', '2025-07-01', '2025-12-31'),
    ]

    conn = sqlite3.connect(str(DB_PATH))
    result = walk_forward_eval(conn, windows, model_type='xgb')

    # Guardar
    out_path = PROJECT_ROOT / "data" / "stacking_walkforward.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n  Guardado en: data/stacking_walkforward.json")


if __name__ == "__main__":
    main()