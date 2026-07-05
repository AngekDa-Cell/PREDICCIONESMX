#!/usr/bin/env python3
"""
Regenera las predicciones BT (backtest) en analyst_predictions con la lógica
de consistencia score↔probs (Ángel, 2026-06-28).

Para cada BT existente:
  1. Lee predicted_home_goals y predicted_away_goals (λ del modelo DC).
  2. Calcula la matriz Poisson completa.
  3. Deriva home_win/draw/away_win sumando marcadores.
  4. Elige el marcador más probable DENTRO del outcome top (consistencia).
  5. Actualiza la fila con los nuevos valores.

Uso:
    cd /workspace/proyectos
    python3 scripts/regenerate_bt_consistency.py [--dry-run]
"""

import sys
import sqlite3
import math
import json
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


def poisson(k, lam):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def recompute(home_goals, away_goals):
    """Recalcula probs 1X2 + score consistente desde λ del modelo."""
    score_probs = {}
    for h in range(8):
        for a in range(8):
            score_probs[(h, a)] = poisson(h, home_goals) * poisson(a, away_goals)
    total = sum(score_probs.values())
    for k in score_probs:
        score_probs[k] /= total if total > 0 else 1.0

    home_win_p = sum(p for (h, a), p in score_probs.items() if h > a)
    draw_p     = sum(p for (h, a), p in score_probs.items() if h == a)
    away_win_p = sum(p for (h, a), p in score_probs.items() if h < a)

    # Score consistente con outcome top
    if home_win_p >= draw_p and home_win_p >= away_win_p:
        outcome = 'home'
        filt = lambda x: x[0] > x[1]
    elif away_win_p >= draw_p and away_win_p >= home_win_p:
        outcome = 'away'
        filt = lambda x: x[0] < x[1]
    else:
        outcome = 'draw'
        filt = lambda x: x[0] == x[1]

    matching = {k: v for k, v in score_probs.items() if filt(k)}
    if matching:
        top_match = max(matching, key=matching.get)
        score = f"{top_match[0]}-{top_match[1]}"
    else:
        score = "0-0"

    confidence = max(home_win_p, draw_p, away_win_p)
    return home_win_p, draw_p, away_win_p, score, confidence, score_probs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no actualizar")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    bt_rows = conn.execute("""
        SELECT id, fixture_id, home_team, away_team,
               home_win, draw, away_win, confidence,
               most_likely_score, predicted_home_goals, predicted_away_goals,
               is_backtest
        FROM analyst_predictions
        WHERE is_backtest = 1
          AND predicted_home_goals IS NOT NULL
          AND predicted_away_goals IS NOT NULL
        ORDER BY match_date
    """).fetchall()

    print(f"📊 {len(bt_rows)} predicciones BT a regenerar\n")

    if not bt_rows:
        print("Nada que hacer.")
        return

    print(f"{'Partido':<35} {'Old probs (L/E/V)':>20} {'New probs':>20} {'Old score':>10} {'New score':>10} {'Old conf':>9} {'New conf':>9}")
    print("-" * 130)

    updates = []
    for row in bt_rows:
        h_team = row["home_team"] or "?"
        a_team = row["away_team"] or "?"
        partido = f"{h_team} vs {a_team}"
        try:
            lh = float(row["predicted_home_goals"])
            la = float(row["predicted_away_goals"])
        except (TypeError, ValueError):
            print(f"  ⚠️ {partido}: λ inválidos, skip")
            continue
        if lh <= 0 or la <= 0:
            print(f"  ⚠️ {partido}: λ<=0, skip")
            continue

        old_h, old_d, old_a = row["home_win"], row["draw"], row["away_win"]
        old_score = row["most_likely_score"] or "?"
        old_conf = row["confidence"]

        new_h, new_d, new_a, new_score, new_conf, score_probs = recompute(lh, la)

        changed = (
            abs((old_h or 0) - new_h) > 0.005 or
            abs((old_d or 0) - new_d) > 0.005 or
            abs((old_a or 0) - new_a) > 0.005 or
            old_score != new_score
        )

        old_probs_str = f"{old_h*100:.0f}/{old_d*100:.0f}/{old_a*100:.0f}" if old_h else "?"
        new_probs_str = f"{new_h*100:.0f}/{new_d*100:.0f}/{new_a*100:.0f}"
        old_conf_str = f"{old_conf*100:.0f}%" if old_conf else "?"
        new_conf_str = f"{new_conf*100:.0f}%"
        marker = "→" if changed else "="
        print(f"  {partido:<33} {old_probs_str:>20} {new_probs_str:>20} {old_score:>10} {new_score:>10} {old_conf_str:>9} {new_conf_str:>9} {marker}")

        # Update features_used con score_probs top-10
        top10 = sorted(score_probs.items(), key=lambda x: -x[1])[:10]
        features_used = json.dumps({
            "score_probs_top10": [
                {"score": f"{h}-{a}", "prob": round(p, 4)} for (h, a), p in top10
            ]
        })

        updates.append((new_h, new_d, new_a, new_conf, new_score, features_used, row["id"]))

    print(f"\n{len(updates)} filas a actualizar.")

    if args.dry_run:
        print("[DRY RUN] No se actualizó nada.")
        return

    for new_h, new_d, new_a, new_conf, new_score, features_used, row_id in updates:
        conn.execute("""
            UPDATE analyst_predictions
            SET home_win = ?, draw = ?, away_win = ?, confidence = ?,
                most_likely_score = ?, features_used = ?
            WHERE id = ?
        """, (round(new_h, 4), round(new_d, 4), round(new_a, 4),
              round(new_conf, 4), new_score, features_used, row_id))
    conn.commit()

    # Verificación final
    print()
    print("=== Verificación post-update ===")
    inconsistentes = 0
    for row in bt_rows:
        c = conn.execute(
            "SELECT home_win, draw, away_win, most_likely_score FROM analyst_predictions WHERE id = ?",
            (row["id"],)
        ).fetchone()
        h, d, a, score = c
        if h is None or score is None:
            continue
        score_h, score_a = int(score[0]), int(score[2])
        if score_h > score_a:
            score_out = "L"
        elif score_h < score_a:
            score_out = "V"
        else:
            score_out = "E"
        if h > d and h > a:
            max_out = "L"
        elif a > d and a > h:
            max_out = "V"
        else:
            max_out = "E"
        if score_out != max_out:
            inconsistentes += 1
            print(f"  ⚠️ {row['home_team']} vs {row['away_team']}: score={score} ({score_out}), max={max_out}")
    if inconsistentes == 0:
        print("  ✓ 0 inconsistencias — probs y marcador 100% consistentes")
    else:
        print(f"  ⚠️ {inconsistentes} inconsistencias restantes")


if __name__ == "__main__":
    main()