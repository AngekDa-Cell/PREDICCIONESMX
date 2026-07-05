"""
backtest_attendance.py — Backtest comparativo CON vs SIN attendance feature.

Usa el backtest estándar (run_backtest) y loopea dos veces:
1. Con attendance_ratio activado (default, heuristic ya integrada)
2. Con attendance_ratio desactivado (heuristic neutralizada temporalmente)

Mide accuracy y Brier para ver si la feature mueve la aguja.
"""
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.backtest import run_backtest, print_summary


def neutralize_attendance_heuristic():
    """Patchea la función heurística de attendance para que no afecte.

    Estrategia: parchear tanto heuristics.apply_heuristics (en el módulo) como
    backtest.apply_heuristics (que ya tiene la referencia importada).

    Para Fase 10 (attendance heur probada en backtest), neutralizamos la heurística
    completa para ver si AÑADE VALOR o RUIDO al ensemble.
    """
    from predict import heuristics, backtest

    # Backup del original (heuristics module)
    original = heuristics.apply_heuristics

    def patched(features, narratives, model_output, *args, **kwargs):
        # Clonar features y neutralizar attendance_ratio
        feat_copy = dict(features)
        feat_copy['attendance_ratio'] = {'available': False}
        return original(feat_copy, narratives, model_output, *args, **kwargs)

    # Parchear AMBAS referencias
    heuristics.apply_heuristics = patched
    backtest.apply_heuristics = patched
    return original


def restore_heuristic(original):
    from predict import heuristics, backtest
    heuristics.apply_heuristics = original
    backtest.apply_heuristics = original


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2024-01-01')
    parser.add_argument('--end', default='2025-12-31')
    parser.add_argument('--use-cache', action='store_true',
                        help='Usar cache de xG precomputado')
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))

    # Test 1: SIN attendance
    print("\n" + "=" * 70)
    print("TEST 1: SIN attendance_ratio (neutralizada)")
    print("=" * 70)
    original = neutralize_attendance_heuristic()
    try:
        summary_no_att = run_backtest(conn, args.start, args.end)
        print_summary(summary_no_att)
    finally:
        restore_heuristic(original)

    # Test 2: CON attendance
    print("\n" + "=" * 70)
    print("TEST 2: CON attendance_ratio (default)")
    print("=" * 70)
    summary_att = run_backtest(conn, args.start, args.end)
    print_summary(summary_att)

    # Comparación
    print("\n" + "=" * 70)
    print("📊 COMPARACIÓN")
    print("=" * 70)
    a = summary_no_att['ensemble']
    b = summary_att['ensemble']
    print(f"  Accuracy  SIN attendance: {a['accuracy']:.4f}")
    print(f"  Accuracy  CON attendance: {b['accuracy']:.4f}")
    print(f"  Δ accuracy:              {b['accuracy'] - a['accuracy']:+.4f} ({(b['accuracy'] - a['accuracy']) * 100:+.2f}pp)")
    print()
    print(f"  Brier     SIN attendance: {a['brier_score']:.4f}")
    print(f"  Brier     CON attendance: {b['brier_score']:.4f}")
    print(f"  Δ Brier:                  {b['brier_score'] - a['brier_score']:+.4f}")
    print()

    # También Brier / accuracy de heurística sola
    if 'heuristic' in a and 'heuristic' in b:
        print(f"  H-only    SIN attendance: {a['heuristic']['accuracy']:.4f} / Brier {a['heuristic']['brier_score']:.4f}")
        print(f"  H-only    CON attendance: {b['heuristic']['accuracy']:.4f} / Brier {b['heuristic']['brier_score']:.4f}")

    # Guardar resultados
    out_dir = PROJECT_ROOT / "data"
    with open(out_dir / "backtest_attendance.json", "w") as f:
        json.dump({
            "start": args.start,
            "end": args.end,
            "without_attendance": summary_no_att,
            "with_attendance": summary_att,
            "delta": {
                "accuracy_pp": round((b['accuracy'] - a['accuracy']) * 100, 2),
                "brier_delta": round(b['brier_score'] - a['brier_score'], 4),
            },
        }, f, indent=2)
    print(f"  Guardado en: data/backtest_attendance.json")


if __name__ == "__main__":
    main()