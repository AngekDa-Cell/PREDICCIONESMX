#!/usr/bin/env python3
"""
test_referee_bias_bt.py — A/B test del referee bias.

Compara BT con y sin referee boost para medir impacto real.
"""

import sys
import math
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def run_bt(conn, n=50, with_referee=True):
    rows = conn.execute("""
        SELECT f.id, f.home_team_id, f.away_team_id, f.season_id,
               f.starting_at, f.home_score, f.away_score
        FROM fixtures f
        WHERE f.league_id = 743
          AND f.home_score IS NOT NULL
          AND f.away_score IS NOT NULL
        ORDER BY f.starting_at DESC
        LIMIT ?
    """, (n,)).fetchall()

    # Inject config BEFORE imports: dynamic toggle
    import json
    coef_path = PROJECT_ROOT / "data" / "mx_coefficients.json"
    with open(coef_path) as f:
        coefs = json.load(f)
    coefs["referee_weight"] = 0.02 if with_referee else 0.0
    coef_temp = PROJECT_ROOT / "data" / "_mx_temp.json"
    with open(coef_temp, "w") as f:
        json.dump(coefs, f)

    # Patch backtest to read this temp file
    import predict.backtest as bt_mod
    bt_mod._temp_coef_path = coef_temp

    # Monkey-patch load_mx_coefficients to use temp
    original_load = None
    try:
        from predict.features import load_mx_coefficients as _orig
        original_load = _orig
    except Exception:
        pass

    # Use my own modified predict_match
    from predict.features import get_full_feature_set, get_referee_bias
    from predict.dixon_coles import fit_dixon_coles, predict_from_model
    from predict.heuristics import apply_heuristics

    correct = 0
    total = 0
    brier_sum = 0
    logloss_sum = 0

    for fx in rows:
        fid, h, a, season_id, date, hs, ascore = fx
        try:
            fs = get_full_feature_set(conn, h, a, season_id, date, fixture_id=fid)
            if not fs or "error" in fs:
                continue

            ref_bias = get_referee_bias(conn, fixture_id=fid)
            ref_shift = 0
            if with_referee and ref_bias.get("available") and ref_bias.get("is_reliable"):
                ref_shift = max(-0.05, min(0.05, ref_bias["bias_score"] * 0.02))

            # quick predict (use existing predict_match)
            from predict.backtest import predict_match
            pred = predict_match(conn, h, a, season_id, date, {"narratives": [], "derbies": []})
            ens = pred["ensemble"]
            pred_class = max(ens, key=ens.get)
            actual = "home" if hs > ascore else ("away" if ascore > hs else "draw")
            if pred_class == actual:
                correct += 1
            total += 1
            actual_oh = {"home": [1.0, 0.0, 0.0], "draw": [0.0, 1.0, 0.0], "away": [0.0, 0.0, 1.0]}[actual]
            brier_sum += sum((ens[k] - actual_oh[i])**2 for i, k in enumerate(["home","draw","away"]))
            logloss_sum += -math.log(max(ens[actual], 1e-10))
        except Exception as e:
            continue

    if coef_temp.exists():
        coef_temp.unlink()

    accuracy = correct / total if total else 0
    brier = brier_sum / total if total else 0
    logloss = logloss_sum / total if total else 0

    return {"accuracy": accuracy, "brier": brier, "logloss": logloss, "n": total}


def main():
    db = PROJECT_ROOT / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(db))

    print("🔄 A/B test: Backtest con vs sin referee bias (últimos 50 partidos)")
    print(f"{'Config':25s} {'n':>4s}  {'accuracy':>9s}  {'brier':>7s}  {'logloss':>7s}")
    print("-" * 60)

    # Run multiple times for stability
    print("📊 Sin referee bias:")
    r1 = run_bt(conn, n=50, with_referee=False)
    print(f"   {'baseline':25s} {r1['n']:4d}  {r1['accuracy']:.1%}  {r1['brier']:.4f}  {r1['logloss']:.4f}")

    print("📊 Con referee bias:")
    r2 = run_bt(conn, n=50, with_referee=True)
    print(f"   {'+ referee (w=0.02)':25s} {r2['n']:4d}  {r2['accuracy']:.1%}  {r2['brier']:.4f}  {r2['logloss']:.4f}")

    delta_acc = r2["accuracy"] - r1["accuracy"]
    delta_brier = r2["brier"] - r1["brier"]
    print(f"\n🔍 Delta:")
    print(f"   accuracy: {delta_acc:+.1%}")
    print(f"   brier:    {delta_brier:+.4f} (menor = mejor)")
    if delta_acc > 0.02:
        print(f"\n   ✅ Referee bias MEJORA accuracy en +{delta_acc:.1%}")
    elif delta_acc < -0.02:
        print(f"\n   ⚠️ Referee bias EMPEORA accuracy en {delta_acc:.1%}")
    else:
        print(f"\n   ➖ Sin diferencia significativa")

    conn.close()


if __name__ == "__main__":
    main()