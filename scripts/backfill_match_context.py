#!/usr/bin/env python3
"""
backfill_match_context.py — Backfill match_context para todos los fixtures históricos.

Llena:
- is_derby (bool) — detecta clásicos MX automáticamente
- is_classic (bool) — TRUE si derby_weight >= 0.8
- psychological_pressure_home/away (float) — basado en forma reciente y contexto

Uso:
  python3 scripts/backfill_match_context.py           # dry run (solo muestra)
  python3 scripts/backfill_match_context.py --apply   # aplicar a la BD
  python3 scripts/backfill_match_context.py --days 30 # solo últimos 30 días
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import sqlite3
from src.predict.heuristics import detect_derby


def get_all_derby_patterns():
    """Known derbies de Liga MX con su peso."""
    return {
        ("América", "Pumas UNAM"): ("Clásico capitalino", 0.9),
        ("Pumas UNAM", "América"): ("Clásico capitalino", 0.9),
        ("Guadalajara", "Atlas"): ("Clásico Tapatío", 0.8),
        ("Atlas", "Guadalajara"): ("Clásico Tapatío", 0.8),
        ("Cruz Azul", "Guadalajara"): ("Clásico nacional", 0.85),
        ("Guadalajara", "Cruz Azul"): ("Clásico nacional", 0.85),
        ("Tigres UANL", "Monterrey"): ("Clásico Regio", 0.9),
        ("Monterrey", "Tigres UANL"): ("Clásico Regio", 0.9),
        ("Pachuca", "Cruz Azul"): ("Clásico Hidalgo", 0.6),
        ("León", "Pachuca"): ("Clásico Miner", 0.5),
        ("Santos Laguna", "Tigres UANL"): ("Clásico Sampson", 0.6),
        ("América", "Cruz Azul"): ("Clásico de México", 0.7),
        ("Pumas UNAM", "Cruz Azul"): ("Clásico universitarios", 0.5),
    }


def compute_context(conn, fixture_id, home_team_id, away_team_id, home_team_name, away_team_name):
    """Calcula match_context para un fixture."""

    # Derby detection
    derby = detect_derby(home_team_name, away_team_name)
    is_derby = derby is not None
    is_classic = is_derby and derby.get("weight", 0) >= 0.8

    # Recent form (últimos 5 partidos) para pressure psicológica
    def recent_form(team_id):
        rows = conn.execute("""
            SELECT f.home_score, f.away_score
            FROM fixtures f
            WHERE f.league_id = 743
              AND f.home_score IS NOT NULL
              AND (f.home_team_id = ? OR f.away_team_id = ?)
              AND f.starting_at < (
                  SELECT starting_at FROM fixtures WHERE id = ?
              )
            ORDER BY f.starting_at DESC
            LIMIT 5
        """, (team_id, team_id, fixture_id)).fetchall()

        if not rows:
            return 0.5  # neutral

        points = 0
        for h, a in rows:
            if (h > a and team_id == home_team_id) or (a > h and team_id == away_team_id):
                points += 3  # win
            elif h == a:
                points += 1  # draw
        return points / (len(rows) * 3)  # 0-1 scale

    home_pressure = recent_form(home_team_id)
    away_pressure = recent_form(away_team_id)

    return {
        "is_derby": 1 if is_derby else 0,
        "is_classic": 1 if is_classic else 0,
        "is_final": 0,  # requiere round name específico
        "is_playoff": 0,  # requiere matchday > 17
        "psychological_pressure_home": round(home_pressure, 3),
        "psychological_pressure_away": round(away_pressure, 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios a la BD (sin esto solo muestra)")
    parser.add_argument("--days", type=int, default=None, help="Solofixtures de los últimos N días")
    parser.add_argument("--limit", type=int, default=None, help="Limitar a N fixtures")
    args = parser.parse_args()

    conn = sqlite3.connect(str(PROJECT_ROOT / "data" / "predictions_mx.db"))
    conn.row_factory = sqlite3.Row

    # Query fixtures
    where = ""
    params = []
    if args.days:
        where = "WHERE f.starting_at >= datetime('now', '-{} days')".format(args.days)
    if args.limit:
        where += (" AND " if where else "WHERE ") + f"f.id IN (SELECT id FROM fixtures LIMIT {args.limit})"

    fixtures = conn.execute(f"""
        SELECT f.id, f.home_team_id, f.away_team_id,
               ht.name as home_name, at.name as away_name
        FROM fixtures f
        JOIN teams ht ON ht.id = f.home_team_id
        JOIN teams at ON at.id = f.away_team_id
        {where}
        ORDER BY f.starting_at DESC
    """, params).fetchall()

    print(f"🔍 Procesando {len(fixtures)} fixtures...")

    existing = conn.execute("SELECT fixture_id FROM match_context").fetchall()
    existing_ids = {r["fixture_id"] for r in existing}
    print(f"   Ya tienen context: {len(existing_ids)} fixtures")

    derby_patterns = get_all_derby_patterns()
    to_insert = []
    to_update = []

    for i, fx in enumerate(fixtures):
        if (i+1) % 200 == 0:
            print(f"   {i+1}/{len(fixtures)}...")

        ctx = compute_context(conn, fx["id"], fx["home_team_id"], fx["away_team_id"],
                              fx["home_name"], fx["away_name"])

        row = {
            "fixture_id": fx["id"],
            **ctx,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        if fx["id"] in existing_ids:
            to_update.append(row)
        else:
            to_insert.append(row)

        # Preview primeros 5 derbies
        if ctx["is_derby"] and len([x for x in to_insert+to_update if x["is_derby"]]) <= 5:
            print(f"   🏟️  [{fx['id']}] {fx['home_name']} vs {fx['away_name']} → derby={ctx.get('is_derby')}")

    print(f"\n📊 Resumen:")
    print(f"   Nuevos:    {len(to_insert)}")
    print(f"   Actualizar: {len(to_update)}")
    derbies = [x for x in to_insert+to_update if x["is_derby"]]
    print(f"   Derbies:   {len(derbies)}")

    if not args.apply:
        print(f"\n⚠️  Modo dry-run. Usa --apply para escribir a la BD.")
        return

    print(f"\n💾 Aplicando cambios...")
    for row in to_insert:
        conn.execute("""
            INSERT INTO match_context
              (fixture_id, is_derby, is_classic, is_final, is_playoff,
               psychological_pressure_home, psychological_pressure_away, last_updated)
            VALUES
              (:fixture_id, :is_derby, :is_classic, :is_final, :is_playoff,
               :psychological_pressure_home, :psychological_pressure_away, :last_updated)
        """, row)

    for row in to_update:
        conn.execute("""
            UPDATE match_context SET
              is_derby = :is_derby,
              is_classic = :is_classic,
              is_final = :is_final,
              is_playoff = :is_playoff,
              psychological_pressure_home = :psychological_pressure_home,
              psychological_pressure_away = :psychological_pressure_away,
              last_updated = :last_updated
            WHERE fixture_id = :fixture_id
        """, row)

    conn.commit()
    print(f"✅ Hecho. {len(to_insert)} insertados, {len(to_update)} actualizados.")


if __name__ == "__main__":
    main()