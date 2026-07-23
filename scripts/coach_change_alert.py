#!/usr/bin/env python3
"""
coach_change_alert.py — Detecta cambios recientes de DT (entrenador) en equipos.

Compara las últimas 2 tenencias por equipo. Si una terminó y otra empezó
recientemente, marca como cambio de DT.

Output: lista de cambios recientes (últimos N días) en formato JSON.
Pensado para que el reporte diario lo incluya.

Uso:
  python3 scripts/coach_change_alert.py
  python3 scripts/coach_change_alert.py --days 7 --json
"""

import sys
import sqlite3
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


def detect_recent_changes(conn, days_back=7):
    """Detecta cambios de DT en los últimos días."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Tenencias que comenzaron recientemente (nuevo DT)
    new_rows = conn.execute("""
        SELECT
            MIN(ct.id) as id, ct.team_id, ct.coach_id, MAX(ct.start_date) as start_date,
            MAX(ct.is_current) as is_current,
            t.name as team_name,
            c.full_name as coach_name
        FROM coach_tenures ct
        JOIN teams t ON t.id = ct.team_id
        LEFT JOIN coaches c ON c.id = ct.coach_id
        WHERE ct.start_date >= ?
          AND t.id IN (
              SELECT id FROM teams WHERE name IN (
                  'América','Atlas','Atlético San Luis','Atlante','Cruz Azul','Guadalajara',
                  'Juárez','León','Mazatlán','Monterrey','Necaxa','Pachuca','Puebla',
                  'Pumas UNAM','Querétaro','Santos Laguna','Tigres UANL','Tijuana','Toluca'
              )
          )
        GROUP BY ct.team_id, ct.coach_id
        ORDER BY start_date DESC
    """, (cutoff,)).fetchall()

    changes = []
    for r in new_rows:
        tenure_id, team_id, coach_id, start, is_current, team_name, coach_name = r
        # Verificar si este equipo tuvo otra tenencia que terminó cerca (cambio real)
        prev = conn.execute("""
            SELECT c.full_name, ct.end_date
            FROM coach_tenures ct
            LEFT JOIN coaches c ON c.id = ct.coach_id
            WHERE ct.team_id = ?
              AND ct.end_date IS NOT NULL
              AND date(ct.end_date) <= date(?)
              AND ct.id != ?
            ORDER BY ct.end_date DESC LIMIT 1
        """, (team_id, start, tenure_id)).fetchone()

        changes.append({
            "team_id": team_id,
            "team_name": team_name,
            "new_coach_id": coach_id,
            "new_coach_name": coach_name or "?",
            "start_date": start,
            "is_current": bool(is_current),
            "previous_coach": prev[0] if prev else None,
            "previous_end_date": prev[1] if prev else None,
            "days_since_change": (datetime.now(timezone.utc).date() - datetime.fromisoformat(start).date()).days if start else None,
        })

    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="Días hacia atrás")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    print(f"🔍 Detectando cambios DT últimos {args.days} días...")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    changes = detect_recent_changes(conn, days_back=args.days)
    conn.close()

    if args.json:
        print(json.dumps(changes, indent=2, ensure_ascii=False))
        return

    if not changes:
        print("✅ Sin cambios de DT recientes.")
        return

    print(f"⚠️  {len(changes)} cambios de DT detectados:\n")
    for c in changes:
        emoji = "🆕" if c["days_since_change"] is not None and c["days_since_change"] <= 3 else "📋"
        prev = f" (antes: {c['previous_coach']})" if c["previous_coach"] else ""
        print(f"{emoji} {c['team_name']:25s} → {c['new_coach_name']} desde {c['start_date']}{prev}")


if __name__ == "__main__":
    main()