"""
backfill_venue_by_team.py — Asigna venue_id a fixtures históricos basándose en equipo local.

Aproximación: cada equipo de Liga MX tiene 1 stadium principal. Asignamos ese
venue a todos sus partidos locales históricos. Es una aproximación — equipos
a veces juegan en venues alternos, pero para weather histórico es suficiente.

Antes: 0 fixtures históricos con venue_id
Después: ~95% con venue_id del equipo local
"""
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
LEAGUE_ID = 743


def get_team_primary_venue(conn):
    """Mapa team_id → venue_id basado en el equipo local más frecuente."""
    # Para cada equipo, encontrar el venue que más ha usado como local
    rows = conn.execute("""
        SELECT home_team_id, venue_id, COUNT(*) as n
        FROM fixtures
        WHERE league_id = ?
          AND home_team_id IS NOT NULL
          AND venue_id IS NOT NULL
        GROUP BY home_team_id, venue_id
        ORDER BY home_team_id, n DESC
    """, (LEAGUE_ID,)).fetchall()

    # Solo el más frecuente por equipo
    team_venue = {}
    for team_id, venue_id, n in rows:
        if team_id not in team_venue:
            team_venue[team_id] = venue_id
    return team_venue


def backfill():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Mapeo team → venue
    team_venue = get_team_primary_venue(conn)
    print(f"📊 {len(team_venue)} equipos con venue principal asignado")

    # Obtener fixtures sin venue
    fixtures = conn.execute("""
        SELECT id, home_team_id
        FROM fixtures
        WHERE league_id = ?
          AND venue_id IS NULL
          AND home_team_id IS NOT NULL
    """, (LEAGUE_ID,)).fetchall()

    print(f"📊 {len(fixtures)} fixtures sin venue_id")

    updated = 0
    skipped = 0

    for f in fixtures:
        venue_id = team_venue.get(f['home_team_id'])
        if venue_id:
            conn.execute(
                "UPDATE fixtures SET venue_id = ? WHERE id = ?",
                (venue_id, f['id'])
            )
            updated += 1
        else:
            skipped += 1

    conn.commit()

    # Verificar
    total = conn.execute("SELECT COUNT(*) FROM fixtures WHERE league_id = ?", (LEAGUE_ID,)).fetchone()[0]
    with_venue = conn.execute("SELECT COUNT(*) FROM fixtures WHERE league_id = ? AND venue_id IS NOT NULL", (LEAGUE_ID,)).fetchone()[0]
    historical_with_venue = conn.execute("""
        SELECT COUNT(*) FROM fixtures
        WHERE league_id = ? AND venue_id IS NOT NULL
          AND home_score IS NOT NULL
    """, (LEAGUE_ID,)).fetchone()[0]

    print()
    print(f"{'='*60}")
    print(f"📊 RESULTADO:")
    print(f"  ✅ Actualizados: {updated}")
    print(f"  ⏭️  Sin venue para su equipo: {skipped}")
    print(f"  📊 Total con venue_id: {with_venue}/{total} ({with_venue/total:.1%})")
    print(f"  📊 Históricos con venue_id: {historical_with_venue}")
    print(f"{'='*60}")

    conn.close()


if __name__ == "__main__":
    backfill()