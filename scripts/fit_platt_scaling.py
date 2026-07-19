#!/usr/bin/env python3
"""
fit_platt_scaling.py — Ajusta Platt scaling para calibrar probabilidades.

Concepto:
  P_calibrated = sigmoid(A * logit(P_raw) + B)

Entrena A, B sobre datos históricos usando validación walk-forward:
  - 4 temporadas de train, 1 de validación (rotando).
  - Out-of-sample Brier = métrica principal.

Aplica calibración 1-vs-rest a las 3 clases (home/draw/away).

Uso:
  python3 scripts/fit_platt_scaling.py --input data/calibration_dataset.csv
  python3 scripts/fit_platt_scaling.py --input ... --target ens  # calibrar ensemble
  python3 scripts/fit_platt_scaling.py --input ... --target elo  # calibrar Elo solo

Output:
  - data/platt_coefficients.json (A, B por clase)
  - Reporte consola: Brier pre vs post calibración (out-of-sample).
"""

import sys
import json
import argparse
import csv
import math
from pathlib import Path
from pathlib import Path
from collections import defaultdict
import numpy as np
from scipy.optimize import minimize
from sklearn.model_selection import KFold

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
COEF_PATH = PROJECT_ROOT / "data" / "platt_coefficients.json"

CLASSES = ["home", "draw", "away"]


def load_dataset(csv_path):
    """Carga dataset de calibración."""
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def actual_to_oh(actual):
    """One-hot encoding del outcome."""
    return {"home": [1.0, 0.0, 0.0], "draw": [0.0, 1.0, 0.0], "away": [0.0, 0.0, 1.0]}[actual]


def sigmoid(x):
    """Sigmoide numéricamente estable."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def platt_apply(p_raw, a, b):
    """Aplica Platt scaling a una prob: p_cal = sigmoid(a*logit(p) + b)."""
    eps = 1e-12
    p = max(eps, min(1.0 - eps, p_raw))
    logit = math.log(p / (1.0 - p))
    return sigmoid(a * logit + b)


def fit_platt_1vrest(probs_raw, outcomes_oh, class_idx):
    """Ajusta (A, B) para clase idx vs resto (regresión logística)."""
    probs = np.array(probs_raw)
    y = np.array([o[class_idx] for o in outcomes_oh])

    # Drop probabilidades muy extremas (clippadas)
    eps = 1e-12
    probs = np.clip(probs, eps, 1.0 - eps)
    logit = np.log(probs / (1.0 - probs))

    def loss(params):
        a, b = params
        # Logistic: y_pred = sigmoid(a*x + b)
        z = a * logit + b
        # Cross entropy
        pred = np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)), np.exp(z) / (1.0 + np.exp(z)))
        ll = -np.mean(y * np.log(pred + eps) + (1 - y) * np.log(1 - pred + eps))
        return ll

    # Inicializar: A=1 (identity), B=0 (no shift)
    res = minimize(loss, [1.0, 0.0], method="L-BFGS-B", bounds=[(-5, 5), (-5, 5)])
    return res.x  # A, B


def normalize_to_3class(probs_dict):
    """Normaliza 3 probs (después de Platt 1vrest) para que sumen 1."""
    total = sum(probs_dict.values())
    return {k: v / total for k, v in probs_dict.items()}


def apply_platt_3class(probs_raw, coefs):
    """Aplica Platt a las 3 clases (1vrest cada una) y renormaliza."""
    out = {}
    eps = 1e-12
    for ci, cls in enumerate(CLASSES):
        a = coefs[cls]["a"]
        b = coefs[cls]["b"]
        out[cls] = platt_apply(probs_raw[cls], a, b)
    total = sum(out.values())
    return {k: v / total for k, v in out.items()}


def brier(predictions, outcomes):
    """Brier score 3-class. predictions: list of {home,draw,away}; outcomes: list of one-hot."""
    total = 0.0
    n = 0
    for p, o in zip(predictions, outcomes):
        for ci, cls in enumerate(CLASSES):
            total += (p[cls] - o[ci]) ** 2
        n += 1
    return total / n if n else float("nan")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="CSV del dataset de calibración")
    parser.add_argument("--target", default="ens",
                        choices=["ens", "elo", "xg", "dc", "heur"],
                        help="A qué modelo aplicamos Platt scaling")
    parser.add_argument("--output-coefs", default=str(COEF_PATH))
    parser.add_argument("--n-folds", type=int, default=5,
                        help="Folds de walk-forward")
    args = parser.parse_args()

    print(f"🎯 PLATT SCALING — target={args.target}")
    print(f"   input: {args.input}")

    rows = load_dataset(args.input)
    print(f"   Cargados: {len(rows)} partidos\n")

    if len(rows) < 100:
        print(f"❌ Muy pocos partidos ({len(rows)}). Necesito n>500 para validar.")
        sys.exit(1)

    # Extraer probs del target
    prefix = args.target  # ens/elo/xg/dc/heur
    probs_raw = []
    outcomes = []
    for r in rows:
        p = {
            "home": float(r[f"{prefix}_home"]),
            "draw": float(r[f"{prefix}_draw"]),
            "away": float(r[f"{prefix}_away"]),
        }
        # Normalizar por si hay drift numérico
        total = sum(p.values())
        p = {k: v/total for k, v in p.items()}
        probs_raw.append(p)
        outcomes.append(actual_to_oh(r["actual"]))

    # Walk-forward por temporada
    by_season = defaultdict(list)
    for r, p, o in zip(rows, probs_raw, outcomes):
        by_season[r["season"]].append((p, o))

    seasons = sorted(by_season.keys())
    print(f"📅 Temporadas en dataset: {seasons}")
    print(f"   n por temporada: { {s: len(v) for s, v in by_season.items()} }\n")

    # Ajuste walk-forward (rotating): entrenar en todas las temp, validar en cada una
    # Pero evaluación out-of-sample = leave-one-season-out

    # 1) GLOBAL: ajustar (A, B) por clase con todos los datos
    print("=" * 60)
    print("1) AJUSTE GLOBAL (todos los datos)")
    print("=" * 60)
    coefs_global = {}
    for ci, cls in enumerate(CLASSES):
        probs_cls = [p[cls] for p in probs_raw]
        a, b = fit_platt_1vrest(probs_cls, outcomes, ci)
        coefs_global[cls] = {"a": float(a), "b": float(b)}
        print(f"   {cls}: A={a:.4f}  B={b:.4f}")

    # 2) Out-of-sample: leave-one-season-out
    print("\n" + "=" * 60)
    print("2) EVALUACIÓN OUT-OF-SAMPLE (leave-one-season-out)")
    print("=" * 60)

    all_pre_brier = []
    all_post_brier = []

    for val_season in seasons:
        train_probs = []
        train_outcomes = []
        val_probs_raw = []
        val_outcomes = []

        for s in seasons:
            for p, o in by_season[s]:
                if s == val_season:
                    val_probs_raw.append(p)
                    val_outcomes.append(o)
                else:
                    train_probs.append(p)
                    train_outcomes.append(o)

        if len(val_probs_raw) < 30:
            print(f"  {val_season}: skipped (n={len(val_probs_raw)} < 30)")
            continue

        # Ajustar Platt en train
        coefs = {}
        for ci, cls in enumerate(CLASSES):
            probs_cls = [p[cls] for p in train_probs]
            a, b = fit_platt_1vrest(probs_cls, train_outcomes, ci)
            coefs[cls] = {"a": float(a), "b": float(b)}

        # Aplicar a val
        val_pred_pre = val_probs_raw
        val_pred_post = [apply_platt_3class(p, coefs) for p in val_probs_raw]

        # Brier
        brier_pre = brier(val_pred_pre, val_outcomes)
        brier_post = brier(val_pred_post, val_outcomes)

        print(f"  {val_season} (n={len(val_probs_raw)}): pre={brier_pre:.4f} post={brier_post:.4f} Δ={(brier_post-brier_pre)*100:+.2f}pp")
        all_pre_brier.append(brier_pre)
        all_post_brier.append(brier_post)

    avg_pre = sum(all_pre_brier) / len(all_pre_brier)
    avg_post = sum(all_post_brier) / len(all_post_brier)
    delta = avg_post - avg_pre
    print()
    print(f"📊 PROMEDIO OOS: pre={avg_pre:.4f} post={avg_post:.4f}  Δ={delta*100:+.2f}pp")

    # Comparar acc pre vs post
    correct_pre = 0
    correct_post = 0
    for p, o in zip(probs_raw, outcomes):
        actual_cls = CLASSES[o.index(1)]
        pick_pre = max(p, key=p.get)
        probs_post = apply_platt_3class(p, coefs_global)
        pick_post = max(probs_post, key=probs_post.get)
        if pick_pre == actual_cls: correct_pre += 1
        if pick_post == actual_cls: correct_post += 1
    acc_pre = correct_pre / len(rows)
    acc_post = correct_post / len(rows)
    print(f"🎯 ACCURACY in-sample (no fair): pre={acc_pre:.1%} post={acc_post:.1%}")
    print(f"   (accuracy cambia cuando Platt cambia el argmax)")

    # Guardar coefs
    output = {
        "_target": args.target,
        "_global_a_b": coefs_global,
        "_note": f"Ajustado 2026-07-19 (Fase B Platt scaling). Out-of-sample Δ Brier={delta*100:+.2f}pp.",
    }
    with open(args.output_coefs, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✅ Coeficientes guardados en {args.output_coefs}")


if __name__ == "__main__":
    main()
