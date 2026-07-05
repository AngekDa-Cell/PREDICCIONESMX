"""
backtest_compare.py — Backtest comparativo de configuraciones.

Compara 4 variantes del modelo:
1. Baseline (sin recalibración)
2. Con recalibración (Platt scaling)
3. Con threshold (skip low-confidence)
4. Con ambas

Reporta métricas: accuracy, Brier, NLL, calibration delta por bucket.

Uso:
  python3 src/predict/backtest_compare.py --start 2025-01-01 --end 2025-12-31
  python3 src/predict/backtest_compare.py --last-n 100
"""
import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.backtest import predict_match
from predict.recalibration import apply_calibration, load_calibration
from predict.heuristics import load_manual_narratives
from predict.misc_utils import get_season_id_for_date


# ─────────────────────────────────────────────────────────────────────────────
# MÉTRICAS
# ─────────────────────────────────────────────────────────────────────────────

def get_actual_result(home_score: int, away_score: int) -> int:
    """0=home, 1=draw, 2=away."""
    if home_score > away_score:
        return 0
    elif home_score < away_score:
        return 2
    return 1


def brier_score(probs_list: List[List[float]], actuals: List[int]) -> float:
    """Brier score multi-class."""
    n = len(probs_list)
    if n == 0:
        return 0.0
    total = 0.0
    for probs, actual in zip(probs_list, actuals):
        for i in range(3):
            target = 1.0 if i == actual else 0.0
            total += (probs[i] - target) ** 2
    return total / n


def log_loss(probs_list: List[List[float]], actuals: List[int]) -> float:
    """Log loss."""
    n = len(probs_list)
    if n == 0:
        return 0.0
    total = 0.0
    for probs, actual in zip(probs_list, actuals):
        p = max(probs[actual], 1e-9)
        total -= math.log(p)
    return total / n


def accuracy(probs_list: List[List[float]], actuals: List[int]) -> float:
    """Accuracy 1X2."""
    if not probs_list:
        return 0.0
    hits = sum(1 for p, a in zip(probs_list, actuals) if p.index(max(p)) == a)
    return hits / len(probs_list)


def calibration_table(
    probs_list: List[List[float]],
    actuals: List[int],
    buckets: List[float] = None,
) -> List[Dict[str, Any]]:
    """Tabla de calibración por bucket de probabilidad."""
    if buckets is None:
        buckets = [0.30, 0.40, 0.50, 0.60, 0.70]

    table = []
    for threshold in buckets:
        # Para cada partido, ¿max_prob está en este bucket?
        bucket_results = []
        for probs, actual in zip(probs_list, actuals):
            max_prob = max(probs)
            predicted_class = probs.index(max_prob)
            if threshold - 0.10 <= max_prob < threshold + 0.10:
                hit = 1 if predicted_class == actual else 0
                bucket_results.append(hit)

        n = len(bucket_results)
        if n == 0:
            actual_rate = None
        else:
            actual_rate = sum(bucket_results) / n

        table.append({
            "bucket": f"{threshold - 0.10:.1f}-{threshold:.1f}",
            "predicted_prob": threshold,
            "n": n,
            "actual_rate": round(actual_rate, 4) if actual_rate is not None else None,
            "delta": round(actual_rate - threshold, 4) if actual_rate is not None else None,
        })

    return table


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST COMPARATIVO
# ─────────────────────────────────────────────────────────────────────────────

def run_comparative_backtest(
    conn: sqlite3.Connection,
    fixtures: List[sqlite3.Row],
    narratives_cache: Dict[int, Dict],
    min_confidence: float = 0.0,
    use_calibration: bool = False,
) -> Dict[str, Any]:
    """Corre backtest con configuración específica."""
    results = []

    for f in fixtures:
        season_id = f['season_id']
        try:
            pred = predict_match(
                conn,
                home_id=f['home_team_id'],
                away_id=f['away_team_id'],
                season_id=season_id,
                fixture_date=str(f['starting_at']),
                narratives=narratives_cache[season_id],
            )
            if pred is None:
                continue
            ensemble = pred['ensemble']

            probs = [ensemble['home'], ensemble['draw'], ensemble['away']]

            # Aplicar recalibración si está habilitada
            if use_calibration:
                cal_probs = apply_calibration({
                    'home_win': probs[0],
                    'draw': probs[1],
                    'away_win': probs[2],
                })
                probs = [cal_probs['home_win'], cal_probs['draw'], cal_probs['away_win']]

            # Threshold: skip si max_prob < min_confidence
            max_prob = max(probs)
            if min_confidence > 0 and max_prob < min_confidence:
                continue

            actual = get_actual_result(f['home_score'], f['away_score'])
            results.append({
                "probs": probs,
                "actual": actual,
                "max_prob": max_prob,
                "home_team_id": f['home_team_id'],
                "away_team_id": f['away_team_id'],
            })
        except Exception:
            continue

    if not results:
        return {"error": "No se generaron predicciones"}

    probs_list = [r["probs"] for r in results]
    actuals = [r["actual"] for r in results]

    return {
        "n_samples": len(results),
        "accuracy": round(accuracy(probs_list, actuals), 4),
        "brier": round(brier_score(probs_list, actuals), 4),
        "log_loss": round(log_loss(probs_list, actuals), 4),
        "calibration_table": calibration_table(probs_list, actuals),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--last-n", type=int, help="Últimos N partidos")
    parser.add_argument("--min-confidence", type=float, default=0.50,
                       help="Threshold mínimo de confianza")
    parser.add_argument("--output", help="Guardar resultados a JSON")
    args = parser.parse_args()

    DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Obtener fixtures
    if args.last_n:
        query = """
            SELECT id, season_id, home_team_id, away_team_id, starting_at,
                   home_score, away_score
            FROM fixtures
            WHERE league_id = 743
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
            ORDER BY starting_at DESC
            LIMIT ?
        """
        fixtures = conn.execute(query, (args.last_n,)).fetchall()
        fixtures = list(reversed(fixtures))  # cronológico
    else:
        query = """
            SELECT id, season_id, home_team_id, away_team_id, starting_at,
                   home_score, away_score
            FROM fixtures
            WHERE league_id = 743
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
              AND starting_at >= ?
              AND starting_at < ?
            ORDER BY starting_at
        """
        fixtures = conn.execute(query, (args.start, args.end)).fetchall()

    print(f"📊 {len(fixtures)} fixtures en rango")

    # Pre-cargar narrativas
    print("⏳ Cargando narrativas...")
    narratives_cache = {}
    season_ids = set(f['season_id'] for f in fixtures)
    for sid in season_ids:
        season_name = conn.execute("SELECT name FROM seasons WHERE id = ?", (sid,)).fetchone()
        if season_name:
            narratives_cache[sid] = load_manual_narratives(season_name['name'].split('/')[0].strip())
        else:
            narratives_cache[sid] = load_manual_narratives()

    # 4 configuraciones
    configs = [
        ("baseline", {"min_confidence": 0.0, "use_calibration": False}),
        ("with_calibration", {"min_confidence": 0.0, "use_calibration": True}),
        ("with_threshold", {"min_confidence": args.min_confidence, "use_calibration": False}),
        ("with_both", {"min_confidence": args.min_confidence, "use_calibration": True}),
    ]

    all_results = {}
    for name, cfg in configs:
        print(f"\n⏳ Corriendo: {name}...")
        result = run_comparative_backtest(
            conn, fixtures, narratives_cache,
            min_confidence=cfg["min_confidence"],
            use_calibration=cfg["use_calibration"],
        )
        all_results[name] = result

    # Imprimir tabla comparativa
    print("\n" + "=" * 80)
    print("📊 BACKTEST COMPARATIVO")
    print("=" * 80)
    print(f"Rango: {args.start if not args.last_n else f'últimos {args.last_n}'} → "
          f"{args.end if not args.last_n else 'hoy'}")
    print(f"Total fixtures: {len(fixtures)}")
    print(f"Threshold: {args.min_confidence:.0%}")
    print(f"Calibración: {'Platt' if load_calibration() else 'ninguna'}")
    print()
    print(f"{'Config':<20} {'N':>6} {'Acc':>8} {'Brier':>8} {'NLL':>8}")
    print("-" * 80)

    for name, _ in configs:
        r = all_results[name]
        if "error" in r:
            print(f"{name:<20} {'-':>6} ERROR: {r['error']}")
            continue
        print(f"{name:<20} {r['n_samples']:>6} {r['accuracy']:>7.2%} {r['brier']:>8.4f} {r['log_loss']:>8.4f}")

    print()
    print("=" * 80)
    print("📈 CALIBRATION (con ambas mejoras):")
    print("=" * 80)
    cal_table = all_results["with_both"].get("calibration_table", [])
    print(f"{'Bucket':<12} {'Predicho':>10} {'N':>6} {'Real':>8} {'Δ':>8}")
    print("-" * 50)
    for row in cal_table:
        actual = row['actual_rate']
        actual_str = f"{actual:.2%}" if actual is not None else "N/A"
        delta = row['delta']
        delta_str = f"{delta:+.2%}" if delta is not None else "N/A"
        print(f"{row['bucket']:<12} {row['predicted_prob']:>9.0%} {row['n']:>6} {actual_str:>8} {delta_str:>8}")

    # Guardar si se pidió
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "config": {
                    "start": args.start,
                    "end": args.end,
                    "min_confidence": args.min_confidence,
                },
                "results": all_results,
            }, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Resultados guardados en {output_path}")

    conn.close()


if __name__ == "__main__":
    main()