"""
backtest_referee.py — Backtest comparativo: ensemble CON vs SIN referee bias.

Optimización: usa xG precompute cache + monkey-patch de get_referee_bias.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.backtest import predict_match, brier_score, log_loss, get_actual_result
from predict import features as _features_mod
import predict.xg as xg_mod


# ─────────────────────────────────────────────────────────────────────────────
# Referee toggle
# ─────────────────────────────────────────────────────────────────────────────


def _neutral_referee_bias(*args, **kwargs) -> Dict[str, Any]:
    return {
        "available": False,
        "is_reliable": False,
        "referee_id": None,
        "name": None,
        "games": 0,
        "bias_score": 0.0,
        "tendency": "unknown",
        "home_win_rate": None,
        "draw_rate": None,
        "away_win_rate": None,
    }


def set_referee_enabled(enabled: bool) -> None:
    """Patch get_referee_bias para devolver neutral cuando enabled=False."""
    if enabled:
        # Restaurar importando original
        import importlib
        importlib.reload(_features_mod) if hasattr(_features_mod, '__file__') else None
    else:
        _features_mod.get_referee_bias = _neutral_referee_bias
        sys.modules["predict.features"].get_referee_bias = _neutral_referee_bias


# ─────────────────────────────────────────────────────────────────────────────
# Métricas
# ─────────────────────────────────────────────────────────────────────────────


def predict_max(probs: Dict[str, float]) -> str:
    return max(probs, key=probs.get)


def metrics_from_results(results: List[Dict]) -> Dict[str, float]:
    """Calcula métricas sobre el ensemble (no los modelos individuales)."""
    n = len(results)
    if n == 0:
        return {"n": 0, "acc": 0, "brier": 0, "nll": 0}
    hits = sum(
        1 for r in results
        if predict_max(r["probs"]["ensemble"]) == r["actual_str"]
    )
    brier_sum = sum(brier_score(r["probs"]["ensemble"], r["actual_str"]) for r in results)
    nll_sum = sum(log_loss(r["probs"]["ensemble"], r["actual_str"]) for r in results)
    return {
        "n": n,
        "acc": hits / n,
        "brier": brier_sum / n,
        "nll": nll_sum / n,
        "n_correct": hits,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────


def run(conn: sqlite3.Connection, start: str, end: str, with_referee: bool) -> Dict[str, Any]:
    """Corre backtest. Retorna dict con 'results' y 'n_with_referee'."""
    import time as _time
    set_referee_enabled(with_referee)

    fixtures = conn.execute(
        """
        SELECT id, season_id, home_team_id, away_team_id, starting_at,
               home_score, away_score
        FROM fixtures
        WHERE league_id IN (743, 749)
          AND home_score IS NOT NULL
          AND starting_at >= ? AND starting_at < ?
        ORDER BY starting_at ASC
        """,
        (start, end),
    ).fetchall()
    print(f"    Total fixtures: {len(fixtures)}")

    narratives = {"narratives": [], "derbies": []}
    results = []
    n_with_ref = 0
    errors = 0

    t0 = _time.time()
    for i, fx in enumerate(fixtures):
        try:
            probs = predict_match(
                conn,
                fx["home_team_id"], fx["away_team_id"],
                fx["season_id"], fx["starting_at"],
                narratives=narratives,
            )
            if probs is None:
                continue
            actual_str = get_actual_result(fx["home_score"], fx["away_score"])

            # Cobertura
            r = conn.execute(
                "SELECT 1 FROM referee_assignments WHERE fixture_id = ? AND type_id = 6",
                (fx["id"],),
            ).fetchone()
            if r:
                n_with_ref += 1

            results.append({
                "fixture_id": fx["id"],
                "actual": actual_str,
                "actual_str": actual_str,
                "probs": probs,
            })
        except Exception as e:
            errors += 1
            if errors < 3:
                import traceback
                print(f"  Error en fixture {fx['id']} ({fx['starting_at']}): {type(e).__name__}: {str(e)[:100]}")
                traceback.print_exc()
            continue

        # Progreso cada 50 partidos
        if (i + 1) % 50 == 0:
            elapsed = _time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(fixtures) - i - 1) / rate if rate > 0 else 0
            print(f"    [{i+1}/{len(fixtures)}] {elapsed:.1f}s | rate={rate:.1f}/s | ETA={eta:.0f}s")

    return {"results": results, "n_with_referee": n_with_ref, "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args()

    print("=" * 70)
    print(f"BACKTEST COMPARATIVO REFEREE — {args.start} → {args.end}")
    print("=" * 70)

    conn = sqlite3.connect("data/predictions_mx.db")
    conn.row_factory = sqlite3.Row
    try:
        # Precomputar xG cache una sola vez
        print("\n[setup] Precomputando xG cache...")
        t0 = time.time()
        xg_cache = xg_mod.precompute_xg_lookup(conn)
        print(f"  → {len(xg_cache['attack'])} equipos ({time.time()-t0:.1f}s)")

        _orig_xg = xg_mod.get_xg_1x2_prediction
        def _xg_cached(conn_, h_, a_, before_date=None, **_):
            return _orig_xg(conn_, h_, a_, before_date=before_date, _cache=xg_cache)
        xg_mod.get_xg_1x2_prediction = _xg_cached
        sys.modules["predict.xg"].get_xg_1x2_prediction = _xg_cached

        # Backtest 1: SIN referee
        print("\n[1/2] Backtest SIN referee bias...")
        t0 = time.time()
        out_no = run(conn, args.start, args.end, with_referee=False)
        m_no = metrics_from_results(out_no["results"])
        print(f"  → {m_no['n']} partidos, acc={100*m_no['acc']:.2f}%, brier={m_no['brier']:.4f} ({time.time()-t0:.1f}s, errors={out_no['errors']})")

        # Backtest 2: CON referee
        print("\n[2/2] Backtest CON referee bias...")
        t0 = time.time()
        out_with = run(conn, args.start, args.end, with_referee=True)
        m_with = metrics_from_results(out_with["results"])
        print(f"  → {m_with['n']} partidos, acc={100*m_with['acc']:.2f}%, brier={m_with['brier']:.4f} ({time.time()-t0:.1f}s, errors={out_with['errors']})")

        # Reporte
        print("\n" + "=" * 70)
        print("RESULTADOS")
        print("=" * 70)
        d_acc = m_with["acc"] - m_no["acc"]
        d_brier = m_with["brier"] - m_no["brier"]
        d_nll = m_with["nll"] - m_no["nll"]
        print(f"\n{'Métrica':<15s} {'Sin ref':>12s} {'Con ref':>12s} {'Δ':>12s}")
        print("-" * 55)
        print(f"{'Accuracy':<15s} {100*m_no['acc']:>11.2f}% {100*m_with['acc']:>11.2f}% {d_acc*100:>+11.2f}pp")
        print(f"{'Brier':<15s} {m_no['brier']:>12.4f} {m_with['brier']:>12.4f} {d_brier:>+12.4f}")
        print(f"{'Log Loss':<15s} {m_no['nll']:>12.4f} {m_with['nll']:>12.4f} {d_nll:>+12.4f}")
        print(f"\nN total: {m_no['n']} | Con referee: {out_with['n_with_referee']} ({100*out_with['n_with_referee']/m_no['n']:.1f}%)")

        # Guardar
        out_path = Path("data/backtest_referee_compare.json")
        out_path.parent.mkdir(exist_ok=True)
        out = {
            "config": {"start": args.start, "end": args.end},
            "without_referee": {**m_no, "n_with_referee": out_no["n_with_referee"], "errors": out_no["errors"]},
            "with_referee": {**m_with, "n_with_referee": out_with["n_with_referee"], "errors": out_with["errors"]},
            "deltas": {
                "accuracy_pp": round(d_acc * 100, 4),
                "brier": round(d_brier, 4),
                "nll": round(d_nll, 4),
            },
        }
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\n→ Guardado en {out_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()