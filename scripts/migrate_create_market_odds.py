#!/usr/bin/env python3
"""
migrate_create_market_odds.py — Migración v3.1: crear tabla market_odds.

Bug detectado 2026-09-10: scripts/ingest_market_odds.py hace
INSERT INTO market_odds pero la tabla no existe en la BD actual
(ni está definida en src/db.py).

Este script crea la tabla con el schema exacto que espera el INSERT
(fixture_id, source, captured_at, home_odds/draw_odds/away_odds,
 home_implied/draw_implied/away_implied, book_vig, meta_json).
Idempotente (IF NOT EXISTS).

Uso:
    python3 scripts/migrate_create_market_odds.py            # aplica
    python3 scripts/migrate_create_market_odds.py --dry-run  # muestra qué haría
"""

import sys
import sqlite3
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"

TABLE_NAME = "market_odds"
CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    home_odds REAL,
    draw_odds REAL,
    away_odds REAL,
    home_implied REAL,
    draw_implied REAL,
    away_implied REAL,
    book_vig REAL,
    meta_json TEXT,
    UNIQUE(fixture_id, source, captured_at),
    FOREIGN KEY(fixture_id) REFERENCES fixtures(id)
)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"❌ BD no existe: {DB_PATH}")
        return 1

    print(f"📂 BD: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE_NAME,),
    ).fetchone()

    if existing:
        print(f"   ✅ Tabla '{TABLE_NAME}' ya existe. Nada que migrar.")
        cols = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        print(f"   Columnas ({len(cols)}): {[c[1] for c in cols]}")
        conn.close()
        return 0

    print(f"   ➕ Tabla '{TABLE_NAME}' NO existe. Creando...")
    if args.dry_run:
        print("🔍 DRY-RUN — no se aplicó.")
        conn.close()
        return 0

    conn.execute(CREATE_SQL)
    conn.commit()

    cols = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    print(f"   ✅ Tabla creada con {len(cols)} columnas: {[c[1] for c in cols]}")
    print(f"   integrity_check: {conn.execute('PRAGMA integrity_check').fetchone()[0]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
