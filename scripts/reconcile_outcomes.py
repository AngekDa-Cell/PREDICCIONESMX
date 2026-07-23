#!/usr/bin/env python3
"""
reconcile_outcomes.py — Reconciliación automática de predicciones live.

Para cada predicción en `analyst_predictions` con is_backtest=0 cuyo fixture
ya terminó, calcula:
  - outcome_hit (1 si el pick acertó)
  - score_hit (1 si el marcador exacto coincide)
  - bts_hit (1 si both teams scored)
  - ou_2_5_hit (1 si over/under 2.5 acertó)
  - actual_home_goals / actual_away_goals (del fixture)
  - result_recorded_at

Uso:
  python3 scripts/reconcile_outcomes.py            # todos los finalizados
  python3 scripts/reconcile_outcomes.py --dry-run  # solo mostrar
"""

import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


def reconcile(conn, dry_run=False):
    """Encuentra predicciones live con fixture finalizado y las reconcilia."""
    # Traer todas las predicciones live cuyo fixture terminó
    rows = conn.execute("""
        SELECT
            ap.id as pred_id,
            ap.fixture_id,
            ap.home_win, ap.draw, ap.away_win,
            ap.confidence,
            ap.most_likely_score,
            f.home_score,
            f.away_score,
            f.starting_at
        FROM analyst_predictions ap
        JOIN fixtures f ON f.id = ap.fixture_id
        WHERE ap.is_backtest = 0
          AND f.home_score IS NOT NULL
          AND f.away_score IS NOT NULL
          AND ap.result_recorded_at IS NULL
    """).fetchall()

    if not rows:
        return 0, 0

    print(f"📊 Predicciones a reconciliar: {len(rows)}")

    updated = 0
    errors = 0

    for r in rows:
        pred_id, fid, h, d, a, conf, mls, hs, as_, starting_at = r

        # Actual outcome
        if hs > as_:
            actual = "home"
        elif as_ > hs:
            actual = "away"
        else:
            actual = "draw"

        # Pick (argmax del ensemble)
        probs = {"home": h, "draw": d, "away": a}
        pick = max(probs, key=probs.get)

        # outcome_hit
        outcome_hit = 1 if pick == actual else 0

        # score_hit (marcador exacto)
        expected_score = mls.replace("-", " ")
        actual_score = f"{hs} {as_}"
        score_hit = 1 if expected_score == actual_score else 0

        # bts_hit (both teams scored)
        bts_hit = 1 if (hs > 0 and as_ > 0) else 0

        # ou_2.5_hit
        total_goals = hs + as_
        if mls and total_goals >= 0:
            # Si el score predicho es implícito del most_likely
            try:
                pred_h, pred_a = map(int, mls.split("-"))
                pred_total = pred_h + pred_a
                if pred_total == total_goals:
                    ou_2_5_hit = 1
                else:
                    # Compara over/under
                    pred_ou = "over" if pred_total >= 3 else "under"
                    actual_ou = "over" if total_goals >= 3 else "under"
                    ou_2_5_hit = 1 if pred_ou == actual_ou else 0
            except (ValueError, AttributeError):
                ou_2_5_hit = None
        else:
            ou_2_5_hit = None

        if dry_run:
            print(f"  {fid}: predicted={pick}, actual={actual}, conf={conf:.2f}, hit={outcome_hit}, score_hit={score_hit}")
            continue

        try:
            conn.execute("""
                UPDATE analyst_predictions
                SET actual_home_goals = ?,
                    actual_away_goals = ?,
                    outcome_hit = ?,
                    score_hit = ?,
                    bts_hit = ?,
                    ou_2_5_hit = ?,
                    result_recorded_at = ?
                WHERE id = ?
            """, (hs, as_, outcome_hit, score_hit, bts_hit, ou_2_5_hit,
                  datetime.now(timezone.utc).isoformat(), pred_id))
            updated += 1
        except Exception as e:
            print(f"  ❌ Error en pred {pred_id}: {e}")
            errors += 1

    if not dry_run:
        conn.commit()

    return updated, errors


def get_accuracy_report(conn, last_n_days=90):
    """Genera reporte de accuracy post-reconciliación."""
    rows = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(outcome_hit) as correct_outcome,
            SUM(score_hit) as correct_score,
            SUM(bts_hit) as correct_bts,
            AVG(confidence) as avg_confidence
        FROM analyst_predictions
        WHERE is_backtest = 0
          AND result_recorded_at IS NOT NULL
          AND datetime(result_recorded_at) >= datetime('now', ?)
    """, (f"-{last_n_days} days",)).fetchone()

    if not rows or rows[0] == 0:
        return None

    total, correct_outcome, correct_score, correct_bts, avg_conf = rows
    return {
        "total": total,
        "outcome_acc": correct_outcome / total if total else 0,
        "score_acc": correct_score / total if total else 0,
        "bts_acc": correct_bts / total if total else 0,
        "avg_confidence": avg_conf,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"🔄 Reconciliación de predicciones — {datetime.now(timezone.utc).isoformat()}")
    print()

    conn = sqlite3.connect(str(DB_PATH))

    updated, errors = reconcile(conn, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"✅ Reconciliadas: {updated}")
        if errors:
            print(f"❌ Errores: {errors}")
        print()
        # Reporte de accuracy
        print("=" * 60)
        print("📊 ACCURACY POST-RECONCILIACIÓN (últimos 90 días)")
        print("=" * 60)
        report = get_accuracy_report(conn, last_n_days=90)
        if report:
            print(f"  Total evaluados: {report['total']}")
            print(f"  Accuracy 1X2: {report['outcome_acc']:.1%} ({int(report['outcome_acc']*report['total'])}/{report['total']})")
            print(f"  Accuracy score exacto: {report['score_acc']:.1%}")
            print(f"  Accuracy BTS: {report['bts_acc']:.1%}")
            print(f"  Confianza promedio: {report['avg_confidence']:.1%}")
        else:
            print("  Sin predicciones finalizadas en últimos 90 días")

    conn.close()


if __name__ == "__main__":
    main()