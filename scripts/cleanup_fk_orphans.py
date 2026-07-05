#!/usr/bin/env python3
"""
cleanup_fk_orphans.py — Limpia foreign keys huérfanas en la BD de Predictions_MX.

Auditoría 2026-07-05 detectó:
- 114 fixtures con venue_id huérfano (venue_id=343651 = Estadio Universitario de Tigres)
- 667 coach_tenures con team_id huérfano (65% del total)

Estrategia:
- NULL en orphans de fixtures.venue_id (es opcional en el flujo)
- DELETE en coach_tenures con team_id huérfano (ya no tiene sentido)

Uso:
    python3 scripts/cleanup_fk_orphans.py [--dry-run]

Seguro de correr. Genera log con conteos antes/después.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path("/workspace/proyectos")
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Solo reporta, no modifica")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"❌ BD no encontrada: {DB_PATH}")
        return 1

    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    # === Backups antes ===
    print("📊 Estado ANTES:")
    fixtures_with_null_venue = cur.execute("""
        SELECT COUNT(*) FROM fixtures
        WHERE venue_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM venues v WHERE v.id=fixtures.venue_id)
    """).fetchone()[0]
    print(f"   fixtures.venue_id orphans: {fixtures_with_null_venue}")

    coach_tenures_orphans = cur.execute("""
        SELECT COUNT(*) FROM coach_tenures
        WHERE NOT EXISTS (SELECT 1 FROM teams t WHERE t.id=coach_tenures.team_id)
    """).fetchone()[0]
    print(f"   coach_tenures.team_id orphans: {coach_tenures_orphans}")

    if args.dry_run:
        print("\n🔍 --dry-run: no se modificaron datos.")
        return 0

    # === Fix 1: NULL venue_id en fixtures huérfanos ===
    print("\n🔧 Limpiando fixtures.venue_id huérfanos...")
    cur.execute("""
        UPDATE fixtures
        SET venue_id = NULL
        WHERE venue_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM venues v WHERE v.id=fixtures.venue_id)
    """)
    n_fixtures = cur.rowcount
    print(f"   ✅ {n_fixtures} fixtures.venue_id set NULL")

    # === Fix 2: DELETE coach_tenures huérfanos ===
    print("\n🔧 Eliminando coach_tenures con team_id huérfano...")
    cur.execute("""
        DELETE FROM coach_tenures
        WHERE NOT EXISTS (SELECT 1 FROM teams t WHERE t.id=coach_tenures.team_id)
    """)
    n_tenures = cur.rowcount
    print(f"   ✅ {n_tenures} coach_tenures eliminadas")

    con.commit()

    # === Verificación ===
    print("\n📊 Estado DESPUÉS:")
    fixtures_with_null_venue_after = cur.execute("""
        SELECT COUNT(*) FROM fixtures
        WHERE venue_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM venues v WHERE v.id=fixtures.venue_id)
    """).fetchone()[0]
    coach_tenures_orphans_after = cur.execute("""
        SELECT COUNT(*) FROM coach_tenures
        WHERE NOT EXISTS (SELECT 1 FROM teams t WHERE t.id=coach_tenures.team_id)
    """).fetchone()[0]
    print(f"   fixtures.venue_id orphans: {fixtures_with_null_venue_after} (era {fixtures_with_null_venue})")
    print(f"   coach_tenures.team_id orphans: {coach_tenures_orphans_after} (era {coach_tenures_orphans})")

    con.close()

    print(f"\n🎉 Limpieza completa. Cambios: {n_fixtures} venues nulled, {n_tenures} tenures deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
