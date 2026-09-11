#!/usr/bin/env python3
"""
migrate_add_outcome_columns.py — Migración v3: agregar outcome columns a analyst_predictions.

Bug detectado 2026-09-10 en dry-run de full_pipeline.py:
- `reconcile_outcomes.py` escribe `outcome_hit`, `score_hit`, `bts_hit`, `ou_2_5_hit`,
  `result_recorded_at`, `actual_home_goals`, `actual_away_goals`
- `full_pipeline.py` paso 10 hace `SUM(outcome_hit)`
- `populate_backtest_historical.py` usa `outcome_hit`
- PERO el schema actual (v2) NO tiene esas columnas → falla en UPDATE y en reporte.

Este script agrega las 7 columnas faltantes con ALTER TABLE (idempotente: si ya existen, skip).

Uso:
    python3 scripts/migrate_add_outcome_columns.py            # aplica
    python3 scripts/migrate_add_outcome_columns.py --dry-run  # muestra qué haría

Pre-requisito: backup de BD (regla dura del proyecto).
"""

import sys
import sqlite3
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"

NEW_COLUMNS = [
    ("actual_home_goals", "INTEGER"),
    ("actual_away_goals", "INTEGER"),
    ("outcome_hit", "INTEGER"),
    ("score_hit", "INTEGER"),
    ("bts_hit", "INTEGER"),
    ("ou_2_5_hit", "INTEGER"),
    ("result_recorded_at", "TEXT"),
]


def existing_columns(conn, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no aplicar")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"❌ BD no existe: {DB_PATH}")
        return 1

    print(f"📂 BD: {DB_PATH}")
    print(f"   dry_run={args.dry_run}")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    pre = existing_columns(conn, "analyst_predictions")
    print(f"   Pre — analyst_predictions tiene {len(pre)} columnas")

    to_add = [(name, typ) for name, typ in NEW_COLUMNS if name not in pre]
    already = [(name, typ) for name, typ in NEW_COLUMNS if name in pre]

    if already:
        print(f"   ✅ Ya presentes ({len(already)}): {[n for n, _ in already]}")
    if to_add:
        print(f"   ➕ A agregar ({len(to_add)}): {[n for n, _ in to_add]}")
    print()

    if not to_add:
        print("🎉 Nada que migrar. Schema ya actualizado.")
        conn.close()
        return 0

    if args.dry_run:
        print("🔍 DRY-RUN — no se aplicaron cambios.")
        conn.close()
        return 0

    # Aplicar ALTERs (SQLite solo permite 1 columna por ALTER)
    for name, typ in to_add:
        sql = f"ALTER TABLE analyst_predictions ADD COLUMN {name} {typ}"
        try:
            conn.execute(sql)
            print(f"   ✓ ALTER ADD COLUMN {name} {typ}")
        except sqlite3.OperationalError as e:
            print(f"   ❌ Falló ALTER {name}: {e}")
            conn.rollback()
            conn.close()
            return 1

    conn.commit()

    post = existing_columns(conn, "analyst_predictions")
    print()
    print(f"   Post — analyst_predictions tiene {len(post)} columnas")
    missing = [n for n, _ in NEW_COLUMNS if n not in post]
    if missing:
        print(f"   ❌ Faltan tras migración: {missing}")
        conn.close()
        return 1
    print(f"   ✅ Todas las columnas presentes: {[n for n, _ in NEW_COLUMNS]}")

    # Integrity check final
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"   integrity_check: {integrity}")

    conn.close()
    print()
    print("🎉 Migración aplicada correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
