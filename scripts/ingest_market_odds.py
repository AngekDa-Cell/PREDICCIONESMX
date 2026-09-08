#!/usr/bin/env python3
"""
ingest_market_odds.py — Ingesta de cuotas de mercado para Liga MX.

Paper base (Frontiers 2025 — Bundesliga xG vs EPV; FanPick 2026 ensemble guide):
  Market odds son el predictor individual más fuerte. Convertir odds a
  implied probabilities = "wisdom of the crowd" sin bias de fan-base.

Estrategia MVP (sin API key):
1. Scraping de BetExplorer.com (odds históricas de closing line)
2. Backup: si scraping falla, calcular implied odds sintético desde
   nuestras predicciones + ruido (~5%) — sirve para backtest CLV.

Tabla: market_odds(fixture_id, source, captured_at, home/draw/away odds + implied)

Uso:
    python3 scripts/ingest_market_odds.py [--source mvp] [--days 14]
"""

import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
import os

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


def implied_probs(home_odds: float, draw_odds: float, away_odds: float):
    """
    Convierte cuotas decimales a implied probabilities SIN VIG.

    BetExplorer / Pinnacle-style:
    1/implied_raw = raw prob
    Total vig = sum(raw probs) - 1.0
    Fair probs = raw / sum(raw)   ← renormalizado

    Returns (home_imp, draw_imp, away_imp, vig_pct).
    """
    raw_h = 1.0 / home_odds
    raw_d = 1.0 / draw_odds
    raw_a = 1.0 / away_odds
    total = raw_h + raw_d + raw_a
    vig_pct = (total - 1.0) * 100  # % de margen
    return (raw_h / total, raw_d / total, raw_a / total, vig_pct)


def synthetic_odds_from_predictions(con: sqlite3.Connection, days_ahead: int = 14):
    """
    Genera odds sintéticos para los próximos N días.

    Útil cuando:
    - No hay API de odds disponible
    - Scraping falla
    - Queremos backtestear con "mercado predecido" vs real

    Strategy: usar nuestras predicciones + ruido gaussiano ~5%.
    """
    rows = con.execute(f"""
        SELECT
            f.id, f.starting_at,
            ap.home_win, ap.draw, ap.away_win
        FROM fixtures f
        LEFT JOIN analyst_predictions ap ON ap.fixture_id = f.id
        WHERE f.home_score IS NULL
        AND f.starting_at BETWEEN datetime('now')
            AND datetime('now', '+{days_ahead} days')
        ORDER BY f.starting_at
    """).fetchall()

    if not rows:
        print(f"   No hay partidos próximos en {days_ahead} días")
        return 0

    import random
    random.seed(42)  # reproducible

    inserted = 0
    for fx_id, starting_at, ph, pd, pa in rows:
        if ph is None or pd is None or pa is None:
            # Sin predicción, usar uniform
            ph, pd, pa = 0.45, 0.27, 0.28
        # Add Gaussian noise ~5% std
        noisy_h = max(0.05, min(0.95, random.gauss(ph, 0.05)))
        noisy_d = max(0.05, min(0.95, random.gauss(pd, 0.03)))
        noisy_a = max(0.05, min(0.95, random.gauss(pa, 0.05)))
        # Normalize
        s = noisy_h + noisy_d + noisy_a
        noisy_h, noisy_d, noisy_a = noisy_h/s, noisy_d/s, noisy_a/s

        # Add bookmaker vig (~5%)
        vig = 1.05
        raw_h, raw_d, raw_a = noisy_h * vig, noisy_d * vig, noisy_a * vig
        s = raw_h + raw_d + raw_a
        imp_h, imp_d, imp_a = raw_h/s, raw_d/s, raw_a/s

        # Convert back to decimal odds (inv)
        home_odds = round(1.0 / imp_h, 2)
        draw_odds = round(1.0 / imp_d, 2)
        away_odds = round(1.0 / imp_a, 2)

        # Insert
        con.execute("""
            INSERT OR REPLACE INTO market_odds
            (fixture_id, source, captured_at, home_odds, draw_odds, away_odds,
             home_implied, draw_implied, away_implied, book_vig, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fx_id, "synthetic_mvp", datetime.utcnow().isoformat() + "Z",
            home_odds, draw_odds, away_odds,
            imp_h, imp_d, imp_a,
            (s - 1.0) * 100,
            json.dumps({"from": "analyst_predictions", "noise_seed": 42}),
        ))
        inserted += 1

    con.commit()
    return inserted


def fetch_from_betexplorer(con: sqlite3.Connection):
    """
    Stub para scraping BetExplorer.com.

    TODO cuando Ángel decida hacer scraping real:
    1. BetExplorer tiene endpoints /match-odds/{fixture-id}.json con histórico
    2. Necesita user-agent rotativo + sleep 1-2s entre requests
    3.Alternativa: usar fbref.com que tiene datos de shot pero no odds

    Por ahora, devuelve 0 (skip) — no fallar.
    """
    print("   ⚠ BetExplorer scraping no implementado en MVP")
    print("      Dejar para sprint B (cuando obtengamos fuente oficial)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["mvp", "betexplorer", "both"], default="both")
    ap.add_argument("--days", type=int, default=14, help="Días hacia adelante")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"❌ BD no encontrada: {DB_PATH}")
        return 1

    print("=" * 60)
    print("📡 INGESTA DE MARKET ODDS — Predictions_MX")
    print("=" * 60)
    print(f"   source={args.source}  days={args.days}")

    con = sqlite3.connect(str(DB_PATH))

    total_inserted = 0

    if args.source in ("mvp", "both"):
        print(f"\n[A] Synthetic MVP odds (próximos {args.days} días)...")
        n = synthetic_odds_from_predictions(con, days_ahead=args.days)
        print(f"   ✅ {n} odds sintéticos insertados")
        total_inserted += n

    if args.source in ("betexplorer", "both"):
        print(f"\n[B] BetExplorer scraping...")
        n = fetch_from_betexplorer(con)
        print(f"   ✅ {n} odds scraped")
        total_inserted += n

    # Reporte
    print(f"\n📊 Total odds en BD: {con.execute('SELECT COUNT(*) FROM market_odds').fetchone()[0]}")
    print("\nÚltimos 5:")
    for r in con.execute("""
        SELECT mo.fixture_id, f.starting_at, mo.source, mo.home_odds, mo.draw_odds, mo.away_odds,
               ROUND(mo.home_implied*100,1), ROUND(mo.book_vig,1)
        FROM market_odds mo
        JOIN fixtures f ON f.id=mo.fixture_id
        ORDER BY mo.captured_at DESC, f.starting_at DESC
        LIMIT 5
    """):
        print(f"   fx={r[0]} when={r[1]} src={r[2]} odds={r[3]}/{r[4]}/{r[5]} h%={r[6]} vig={r[7]}%")

    con.close()

    print(f"\n🎯 {total_inserted} odds nuevas insertadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
