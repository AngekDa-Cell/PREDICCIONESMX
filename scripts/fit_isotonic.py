#!/usr/bin/env python3
"""
fit_isotonic.py — Ajusta Isotonic Regression para calibrar probabilidades.

Compara Platt (logístico) vs Isotonic (no-paramétrico) vía OOS validation.
Isotonic es más flexible — puede capturar no-linealidades — pero también
más propenso a overfit en muestra pequeña.

Para cada clase (home/draw/away) ajusta 1 IsotonicRegression sobre
probs_raw → outcome_oh[clase] (1-vs-rest).

Evalúa OOS Brier + Accuracy y reporta comparación contra Platt (si existe).

Output: data/isotonic_coefficients.json con los 3 modelos serializados.
"""

import sys
import json
import pickle
import argparse
import csv
import math
import base64
from pathlib import Path
from pathlib import Path
from collections import defaultdict
import numpy as np
from sklearn.isotonic import IsotonicRegression

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

CLASSES = ["home", "draw", "away"]
COEFS_PATH = PROJECT_ROOT / "data" / "isotonic_coefficients.json"
PLATT_PATH = PROJECT_ROOT / "data" / "platt_coefficients.json"


def load_dataset(csv_path):
    rows = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def actual_to_oh(actual):
    return {"home": [1.0, 0.0, 0.0], "draw": [0.0, 1.0, 0.0], "away": [0.0, 0.0, 1.0]}[actual]


def fit_isotonic_1vrest(probs_raw, y_outcomes):
    """Ajusta IsotonicRegression para 1 clase.

    Args:
        probs_raw: lista de probs crudas para esta clase.
        y_outcomes: lista de outcomes (0/1) para esta clase.
    """
    probs = np.array([float(x) for x in probs_raw], dtype=np.float64)
    y = np.array([float(v) for v in y_outcomes], dtype=np.float64)
    eps = 1e-12
    probs = np.clip(probs, eps, 1 - eps)
    ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    ir.fit(probs, y)
    return ir


def apply_isotonic_3class(probs_raw, isotonic_models):
    """Aplica las 3 IsotonicRegression 1vrest y renormaliza."""
    out = {}
    for ci, cls in enumerate(CLASSES):
        out[cls] = float(isotonic_models[cls].predict([probs_raw[cls]])[0])
    total = sum(out.values())
    if total <= 0:
        # Fallback: igual probs (no se debe renombrar si todo es 0)
        return probs_raw
    return {k: v / total for k, v in out.items()}


def brier(predictions, outcomes):
    total = 0.0
    for p, o in zip(predictions, outcomes):
        for ci, cls in enumerate(CLASSES):
            total += (p[cls] - o[ci]) ** 2
    return total / len(predictions) / 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--target", default="ens", choices=["ens", "elo", "xg", "dc", "heur"])
    parser.add_argument("--output-coefs", default=str(COEFS_PATH))
    parser.add_argument("--compare-platt", action="store_true",
                        help="Comparar OOS contra platt_coefficients.json")
    args = parser.parse_args()

    print(f"🎯 ISOTONIC REGRESSION — target={args.target}")
    print(f"   input: {args.input}")

    rows = load_dataset(args.input)
    print(f"   Cargados: {len(rows)} partidos\n")

    if len(rows) < 200:
        print(f"❌ Muy pocos ({len(rows)}). Necesito n>500.")
        sys.exit(1)

    # Extraer probs del target
    prefix = args.target
    probs_raw = []
    outcomes = []
    for r in rows:
        p = {
            "home": float(r[f"{prefix}_home"]),
            "draw": float(r[f"{prefix}_draw"]),
            "away": float(r[f"{prefix}_away"]),
        }
        total = sum(p.values())
        p = {k: v / total for k, v in p.items()}
        probs_raw.append(p)
        outcomes.append(actual_to_oh(r["actual"]))

    by_season = defaultdict(list)
    for r, p, o in zip(rows, probs_raw, outcomes):
        by_season[r["season"]].append((p, o))

    seasons = sorted(by_season.keys())
    print(f"📅 Temporadas: {seasons}")

    # Walk-forward: leave-one-season-out
    print("\n" + "=" * 60)
    print("EVALUACIÓN OOS (leave-one-season-out) — ISOTONIC")
    print("=" * 60)

    all_pre = []
    all_post_iso = []
    final_models = {}  # última iteración para guardar

    for val_season in seasons:
        train_p = []
        train_y = {c: [] for c in CLASSES}
        val_p = []
        val_outcomes = []

        for s in seasons:
            for p, o in by_season[s]:
                if s == val_season:
                    val_p.append(p)
                    val_outcomes.append(o)
                else:
                    train_p.append(p)
                    for ci, cls in enumerate(CLASSES):
                        train_y[cls].append(o[ci])

        if len(val_p) < 30:
            continue

        # Fit Isotonic por clase
        iso_models = {}
        for cls in CLASSES:
            iso_models[cls] = fit_isotonic_1vrest(
                [p[cls] for p in train_p], train_y[cls]
            )

        # Apply
        val_post = [apply_isotonic_3class(p, iso_models) for p in val_p]

        b_pre = brier(val_p, val_outcomes)
        b_post = brier(val_post, val_outcomes)
        delta = (b_post - b_pre) * 100
        print(f"  {val_season} (n={len(val_p)}): pre={b_pre:.4f} post={b_post:.4f} Δ={delta:+.2f}pp")
        all_pre.append(b_pre)
        all_post_iso.append(b_post)
        final_models = iso_models  # última para guardar

    avg_pre = sum(all_pre) / len(all_pre)
    avg_post = sum(all_post_iso) / len(all_post_iso)
    print(f"\n📊 Isotonic OOS promedio: pre={avg_pre:.4f} post={avg_post:.4f} Δ={(avg_post - avg_pre) * 100:+.2f}pp")

    # Accuracy OOS
    correct_pre = correct_post = 0
    n = 0
    for s in seasons:
        for p, actual in [(p, o) for p, o in by_season[s] for _ in [None]]:
            pass
    # Recompute accuracy OOS properly
    for val_season in seasons:
        train_p = []
        train_y = {c: [] for c in CLASSES}
        val_p = []
        val_actuals = []
        for s in seasons:
            for p, o in by_season[s]:
                actual = o
                if s == val_season:
                    val_p.append(p)
                    val_actuals.append(CLASSES[o.index(1.0)])
                else:
                    train_p.append(p)
                    for ci, cls in enumerate(CLASSES):
                        train_y[cls].append(o[ci])
        if len(val_p) < 30:
            continue
        iso_models = {}
        for cls in CLASSES:
            iso_models[cls] = fit_isotonic_1vrest([p[cls] for p in train_p], train_y[cls])
        for p, actual in zip(val_p, val_actuals):
            if max(p, key=p.get) == actual:
                correct_pre += 1
            p_post = apply_isotonic_3class(p, iso_models)
            if max(p_post, key=p_post.get) == actual:
                correct_post += 1
            n += 1
    acc_pre = correct_pre / n
    acc_post = correct_post / n
    print(f"🎯 Accuracy OOS: pre={acc_pre:.1%} post={acc_post:.1%} Δ={(acc_post - acc_pre) * 100:+.2f}pp")

    # Fit final con todos los datos
    final_iso = {}
    for cls in CLASSES:
        # outcomes es lista de listas one-hot [home, draw, away]
        cls_idx = CLASSES.index(cls)
        final_iso[cls] = fit_isotonic_1vrest(
            [p[cls] for p in probs_raw],
            [o[cls_idx] for o in outcomes],
        )

    # Guardar
    serialized = {}
    for cls, ir in final_iso.items():
        # Serializar pares (threshold, value) — sklearn no se pickle-b64 directo
        # pero podemos guardar los puntos de la curva monotónica
        thresholds = ir.X_thresholds_
        values = ir.y_thresholds_
        # Filtrar duplicados (sklearn puede tener repeats)
        # Serializar como base64 de pickle (compatibilidad completa)
        pkl_bytes = pickle.dumps(ir)
        serialized[cls] = {
            "method": "isotonic",
            "pickle_b64": base64.b64encode(pkl_bytes).decode("ascii"),
            "thresholds": thresholds.tolist() if hasattr(thresholds, "tolist") else list(thresholds),
            "values": values.tolist() if hasattr(values, "tolist") else list(values),
        }

    output = {
        "_target": args.target,
        "_global_iso": serialized,
        "_note": f"Isotonic regression calibrada 2026-07-19 (Fase B). OOS Brier pre={avg_pre:.4f} post={avg_post:.4f} Δ={(avg_post-avg_pre)*100:+.2f}pp. Acc OOS pre={acc_pre:.1%} post={acc_post:.1%}.",
        "_oos_brier_pre": avg_pre,
        "_oos_brier_post": avg_post,
        "_oos_brier_delta_pp": (avg_post - avg_pre) * 100,
        "_oos_acc_pre": acc_pre,
        "_oos_acc_post": acc_post,
        "_n_fit": len(rows),
        "_generated_at": __import__("datetime").datetime.now().isoformat(),
    }
    with open(args.output_coefs, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✅ Coeficientes isotonic guardados en {args.output_coefs}")

    # Comparar contra Platt si existe
    if PLATT_PATH.exists():
        try:
            with open(PLATT_PATH) as f:
                platt = json.load(f)
            # Platt usa Brier total/n (sin /3); isotonic usa total/(n*3).
            # Normalizar ambos a escala total/(n*3) para apple-to-apple.
            p_pre = platt.get("_oos_brier_pre", 0) / 3
            p_post = platt.get("_oos_brier_post", 0) / 3
            p_acc = platt.get("_oos_acc_post", 0)  # 0 si no guardado
            i_post = avg_post
            i_acc = acc_post
            print(f"\n📢 COMPARACIÓN PLATT vs ISOTONIC (Brier normalizado por n*k)")
            print(f"                       Platt       Isotonic   Ganador")
            print(f"   Brier pre:        {p_pre:.4f}      {avg_pre:.4f}     {'Platt' if p_pre < avg_pre else 'Isotonic' if avg_pre < p_pre else 'TIE'}")
            print(f"   Brier post:       {p_post:.4f}      {i_post:.4f}     {'Platt' if p_post < i_post else 'Isotonic' if i_post < p_post else 'TIE'}")
            print(f"   Acc OOS post:     {p_acc:>4.1%}      {i_acc:.1%}     {'Platt' if p_acc > i_acc else 'Isotonic' if i_acc > p_acc else 'TIE'}")
        except Exception as e:
            print(f"⚠️  No pude comparar contra Platt: {e}")


if __name__ == "__main__":
    main()
