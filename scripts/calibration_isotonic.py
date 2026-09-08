#!/usr/bin/env python3
"""
calibration_isotonic.py — Calibración post-hoc con Isotonic Regression.

Paper base (exprysm.com):
  "An overconfident model systematically identifies 'value' that doesn't exist.
   Over hundreds of bets, this destroys your bankroll."
  → Calibration > Accuracy.

Estrategia walk-forward:
1. Train: 70% antiguo de partidos finalizados con predicción + outcome real
2. Calib: 30% reciente (holdout)
3. Fit isotonic por outcome: home_win, draw, away_win
4. Midir Brier antes/después

Uso:
    python3 scripts/calibration_isotonic.py
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import os

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
OUT_PATH = PROJECT_ROOT / "data" / "isotonic_calibration.json"
REPORT_PATH = PROJECT_ROOT / "data" / "calibration_report.json"


def fetch_predictions(con: sqlite3.Connection) -> list:
    """Trae predicciones de partidos FT con outcome real."""
    rows = con.execute("""
        SELECT
            ap.id, ap.fixture_id,
            ap.home_win, ap.draw, ap.away_win,
            f.home_score, f.away_score,
            ap.created_at, f.starting_at
        FROM analyst_predictions ap
        JOIN fixtures f ON f.id = ap.fixture_id
        WHERE f.home_score IS NOT NULL
        AND f.away_score IS NOT NULL
        AND ap.home_win IS NOT NULL
        AND ap.draw IS NOT NULL
        AND ap.away_win IS NOT NULL
        ORDER BY f.starting_at ASC
    """).fetchall()
    return rows


def outcome_vector(home_score: int, away_score: int) -> tuple:
    """Devuelve (1, 0, 0) si gana local, etc."""
    if home_score > away_score:
        return (1, 0, 0)
    elif home_score < away_score:
        return (0, 0, 1)
    return (0, 1, 0)


def brier_score(probs: list, outcomes: list) -> float:
    """Brier = mean((p - o)^2). Para multiclass se suman los 3 outcomes."""
    n = len(probs)
    s = 0.0
    for p, o in zip(probs, outcomes):
        # p is (p_home, p_draw, p_away); o is (o_home, o_draw, o_away)
        for i in range(3):
            s += (p[i] - o[i]) ** 2
    return s / n


def main():
    print("=" * 60)
    print("📐 CALIBRACIÓN ISOTONIC — Predictions_MX")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"❌ BD no encontrada: {DB_PATH}")
        return 1

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    rows = fetch_predictions(con)
    con.close()

    if len(rows) < 30:
        print(f"⚠ Solo {len(rows)} predicciones con outcome. Necesitamos >=30 para calibrar.")
        print(f"   Esperar más jornadas de Liga MX para calibración robusta.")
        return 2

    # Preparar datos
    probs = [(r["home_win"], r["draw"], r["away_win"]) for r in rows]
    outcomes = [outcome_vector(r["home_score"], r["away_score"]) for r in rows]

    print(f"\n[1] Datos: {len(rows)} partidos finalizados con predicción")
    print(f"    Train cutoff: 70% ({int(0.7 * len(rows))} train, {len(rows) - int(0.7 * len(rows))} calib)")

    # Split walk-forward
    n_train = int(0.7 * len(rows))
    train_p, train_o = probs[:n_train], outcomes[:n_train]
    calib_p, calib_o = probs[n_train:], outcomes[n_train:]

    # Brier baseline (sin calibración)
    brier_baseline_train = brier_score(train_p, train_o)
    brier_baseline_calib = brier_score(calib_p, calib_o)
    print(f"\n[2] Brier ANTES de calibración:")
    print(f"    Train: {brier_baseline_train:.4f}")
    print(f"    Calib: {brier_baseline_calib:.4f}")

    # Fit isotonic — sklearn
    try:
        from sklearn.isotonic import IsotonicRegression
        import numpy as np
    except ImportError:
        print("❌ sklearn no instalado. pip install scikit-learn")
        return 3

    # Calibramos CADA outcome por separado (1-vs-rest)
    cal_models = {}
    for i, label in enumerate(["home_win", "draw", "away_win"]):
        x = np.array([p[i] for p in train_p])
        y = np.array([o[i] for o in train_o])
        if y.sum() < 3:
            print(f"   ⚠ {label}: solo {int(y.sum())} ocurrencias en train — saltando isotonic")
            continue
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
        iso.fit(x, y)
        cal_models[label] = iso

    # Aplicar calibración al set de calibración
    if not cal_models:
        print("❌ Ningún modelo se calibró. Datos insuficientes.")
        return 4

    calib_p_calib = []
    for p in calib_p:
        new = []
        for i, label in enumerate(["home_win", "draw", "away_win"]):
            if label in cal_models:
                v = cal_models[label].predict([p[i]])[0]
                new.append(v)
            else:
                new.append(p[i])
        # Renormalizar para que sume 1.0
        s = sum(new)
        new = [v / s for v in new]
        calib_p_calib.append(tuple(new))

    brier_calib_after = brier_score(calib_p_calib, calib_o)
    improvement = brier_baseline_calib - brier_calib_after
    print(f"\n[3] Brier DESPUÉS de calibración isotonic:")
    print(f"    Calib: {brier_calib_after:.4f}")
    print(f"    Δ: {'+' if improvement > 0 else ''}{improvement:.4f} {'✅ mejor' if improvement > 0 else '⚠️ no mejoró'}")

    # Guardar modelo
    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_train": len(train_p),
        "n_calib": len(calib_p),
        "brier_baseline": {
            "train": brier_baseline_train,
            "calib": brier_baseline_calib,
        },
        "brier_isotonic": {
            "calib": brier_calib_after,
            "improvement": improvement,
        },
        "outcomes_available": list(cal_models.keys()),
    }

    # Serializar modelos — guardar thresholds/breakpoints
    for label, iso in cal_models.items():
        out[f"iso_{label}"] = {
            "thresholds": iso.X_thresholds_.tolist(),
            "values": iso.y_thresholds_.tolist(),
        }

    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\n💾 Calibrador guardado en {OUT_PATH.name}")

    # Reporte
    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "n_total": len(rows),
        "n_train": len(train_p),
        "n_calib": len(calib_p),
        "brier_baseline_calib": brier_baseline_calib,
        "brier_isotonic_calib": brier_calib_after,
        "delta": improvement,
        "verdict": "BETER" if improvement > 0.01 else ("NEUTRAL" if improvement > 0 else "WORSE"),
        "outcomes_calibrated": list(cal_models.keys()),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"📋 Reporte guardado en {REPORT_PATH.name}")

    print(f"\n🎯 Veredicto: {report['verdict']}")
    if improvement > 0.01:
        print("   → Recomiendo aplicar isotonic al pipeline de predicciones.")
    else:
        print("   → Calibración marginal. Esperar más datos (>=50 partidos reales).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
