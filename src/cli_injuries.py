#!/usr/bin/env python3
"""
cli_injuries.py — CLI para gestionar lesiones manualmente.

Útil cuando:
- ESPN no tiene la lesión (medios MX se enteran primero)
- Backtest retrospectivo (necesitamos lesiones históricas)
- Casos específicos (suspensión, nacional, etc.)

Uso:
    python3 src/cli_injuries.py add --team "América" --player "Henry Martín" \\
        --severity Out --type "Lesión muscular" --start 2026-05-01

    python3 src/cli_injuries.py list [--team "América"] [--active-only]

    python3 src/cli_injuries.py end --injury-id 12 --end-date 2026-06-15

    python3 src/cli_injuries.py bulk --json injuries_batch.json
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, date

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


def find_player(conn, team_id, player_name):
    """Busca jugador por fuzzy match."""
    name_lower = player_name.lower().strip()
    # Try exact match
    row = conn.execute(
        """
        SELECT id, full_name, primary_position
        FROM players
        WHERE JSON_EXTRACT(meta_json, '$.team_id') = ?
          AND (LOWER(full_name) = ? OR LOWER(common_name) = ?)
        LIMIT 1
        """,
        (team_id, name_lower, name_lower),
    ).fetchone()
    if row:
        return row
    # Partial match (last name)
    parts = name_lower.split()
    if len(parts) >= 2:
        last = parts[-1]
        row = conn.execute(
            """
            SELECT id, full_name, primary_position
            FROM players
            WHERE JSON_EXTRACT(meta_json, '$.team_id') = ?
              AND (LOWER(last_name) LIKE ? OR LOWER(full_name) LIKE ?)
            LIMIT 1
            """,
            (team_id, f"%{last}%", f"%{name_lower}%"),
        ).fetchone()
        if row:
            return row
    return None


def find_team(conn, team_name):
    """Busca equipo por fuzzy match."""
    name_lower = team_name.lower().strip()
    row = conn.execute(
        "SELECT id, name FROM teams WHERE LOWER(name) = ? LIMIT 1",
        (name_lower,),
    ).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT id, name FROM teams WHERE LOWER(name) LIKE ? LIMIT 1",
        (f"%{name_lower}%",),
    ).fetchone()
    return row


def get_current_season(conn):
    row = conn.execute(
        "SELECT id FROM seasons WHERE is_current = 1 ORDER BY start_date DESC LIMIT 1"
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT id FROM seasons ORDER BY start_date DESC LIMIT 1"
    ).fetchone()
    return row[0]


def cmd_add(args):
    conn = sqlite3.connect(str(DB_PATH))

    team = find_team(conn, args.team)
    if not team:
        print(f"❌ Equipo '{args.team}' no encontrado")
        conn.close()
        return 1

    player_id = None
    pos = ""
    if args.player:
        player = find_player(conn, team[0], args.player)
        if player:
            player_id, full_name, pos = player
            print(f"✓ Jugador: {full_name} ({pos})")
        else:
            print(f"⚠️  Jugador '{args.player}' no matcheado en BD — guardo lesión sin player_id")
            print(f"   (igual funciona si lo llenas a mano después)")

    season_id = get_current_season(conn)

    meta = {
        "source": "manual",
        "added_by": "angel",
        "added_at": datetime.now().isoformat(),
        "notes": args.notes or "",
    }

    cur = conn.execute(
        """
        INSERT INTO player_injuries
            (player_id, team_id, season_id, start_date, end_date,
             injury_type, severity, source, meta_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            player_id,
            team[0],
            season_id,
            args.start,
            args.end,
            args.type or "Unknown",
            args.severity or "Out",
            "manual",
            json.dumps(meta),
        ),
    )
    conn.commit()
    print(f"✅ Lesión #{cur.lastrowid} agregada: {args.player or '?'} ({team[1]}) — {args.severity}")
    conn.close()
    return 0


def cmd_list(args):
    conn = sqlite3.connect(str(DB_PATH))

    sql = """
        SELECT
            pi.id, pi.start_date, pi.end_date, pi.injury_type, pi.severity,
            t.name, p.full_name, p.common_name, p.primary_position
        FROM player_injuries pi
        LEFT JOIN teams t ON t.id = pi.team_id
        LEFT JOIN players p ON p.id = pi.player_id
        WHERE 1=1
    """
    params = []

    if args.team:
        team = find_team(conn, args.team)
        if team:
            sql += " AND pi.team_id = ?"
            params.append(team[0])
        else:
            print(f"❌ Equipo '{args.team}' no encontrado")
            conn.close()
            return 1

    if args.active_only:
        sql += " AND (pi.end_date IS NULL OR pi.end_date >= date('now'))"

    sql += " ORDER BY pi.start_date DESC"

    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    rows = conn.execute(sql, params).fetchall()

    if not rows:
        print("Sin lesiones registradas")
        conn.close()
        return 0

    print(f"{'ID':>4}  {'Inicio':12s}  {'Fin':12s}  {'Equipo':25s}  {'Jugador':30s}  {'Sev':12s}  {'Tipo'}")
    print("-" * 120)
    for r in rows:
        iid, start, end, itype, sev, team_name, full, common, pos = r
        name = full or common or "?"
        print(f"{iid:>4}  {str(start):12s}  {str(end or '-'):12s}  {team_name:25s}  {name[:30]:30s}  {sev or '-':12s}  {itype}")

    print(f"\nTotal: {len(rows)}")
    conn.close()
    return 0


def cmd_end(args):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "UPDATE player_injuries SET end_date = ? WHERE id = ?",
        (args.end_date, args.injury_id),
    )
    if conn.total_changes == 0:
        print(f"❌ Lesión #{args.injury_id} no encontrada")
    else:
        print(f"✅ Lesión #{args.injury_id} marcada como terminada en {args.end_date}")
    conn.commit()
    conn.close()
    return 0


def cmd_bulk(args):
    """Inserta lesiones desde un JSON."""
    conn = sqlite3.connect(str(DB_PATH))
    with open(args.json) as f:
        injuries = json.load(f)

    season_id = get_current_season(conn)
    inserted = 0
    failed = 0

    for inj in injuries:
        team = find_team(conn, inj["team"])
        if not team:
            print(f"❌ Equipo no encontrado: {inj['team']}")
            failed += 1
            continue

        player_id = None
        pos = ""
        if "player" in inj:
            player = find_player(conn, team[0], inj["player"])
            if player:
                player_id, full_name, pos = player
            else:
                print(f"⚠️  Jugador no matcheado: {inj.get('player')} ({inj['team']})")

        meta = {
            "source": "manual_bulk",
            "added_at": datetime.now().isoformat(),
            "notes": inj.get("notes", ""),
            "display_name": inj.get("player", ""),
        }

        try:
            conn.execute(
                """
                INSERT INTO player_injuries
                    (player_id, team_id, season_id, start_date, end_date,
                     injury_type, severity, source, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    player_id,
                    team[0],
                    season_id,
                    inj["start"],
                    inj.get("end"),
                    inj.get("type", "Unknown"),
                    inj.get("severity", "Out"),
                    "manual_bulk",
                    json.dumps(meta),
                ),
            )
            inserted += 1
        except Exception as e:
            print(f"❌ Error insertando {inj}: {e}")
            failed += 1

    conn.commit()
    conn.close()
    print(f"\n✅ Insertadas: {inserted} · ❌ Fallidas: {failed}")
    return 0 if failed == 0 else 1


def cmd_clear(args):
    """Borra lesiones (CUIDADO)."""
    if not args.confirm:
        print("⚠️  Necesitas --confirm para borrar")
        return 1
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(f"DELETE FROM player_injuries WHERE source = ?", (args.source,))
    conn.commit()
    print(f"✅ Borradas {cur.rowcount} lesiones con source='{args.source}'")
    conn.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="CLI de lesiones manuales")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # add
    p_add = sub.add_parser("add", help="Agregar lesión manual")
    p_add.add_argument("--team", required=True, help="Nombre del equipo")
    p_add.add_argument("--player", required=True, help="Nombre del jugador")
    p_add.add_argument("--severity", default="Out",
                       choices=["Out", "Doubtful", "Questionable", "Day-To-Day", "Probable"])
    p_add.add_argument("--type", default="Lesión", help="Tipo (Lesión muscular, Esguince, etc.)")
    p_add.add_argument("--start", required=True, help="Fecha inicio (YYYY-MM-DD)")
    p_add.add_argument("--end", help="Fecha fin (YYYY-MM-DD, opcional)")
    p_add.add_argument("--notes", help="Notas adicionales")

    # list
    p_list = sub.add_parser("list", help="Listar lesiones")
    p_list.add_argument("--team", help="Filtrar por equipo")
    p_list.add_argument("--active-only", action="store_true", help="Solo activas")
    p_list.add_argument("--limit", type=int, help="Máx resultados")

    # end
    p_end = sub.add_parser("end", help="Marcar lesión como terminada")
    p_end.add_argument("--injury-id", type=int, required=True)
    p_end.add_argument("--end-date", required=True, help="YYYY-MM-DD")

    # bulk
    p_bulk = sub.add_parser("bulk", help="Insertar desde JSON")
    p_bulk.add_argument("--json", required=True, help="Path al JSON")

    # clear
    p_clear = sub.add_parser("clear", help="Borrar lesiones (CUIDADO)")
    p_clear.add_argument("--source", default="manual", help="Source a borrar")
    p_clear.add_argument("--confirm", action="store_true")

    args = parser.parse_args()

    if args.cmd == "add":
        return cmd_add(args)
    elif args.cmd == "list":
        return cmd_list(args)
    elif args.cmd == "end":
        return cmd_end(args)
    elif args.cmd == "bulk":
        return cmd_bulk(args)
    elif args.cmd == "clear":
        return cmd_clear(args)


if __name__ == "__main__":
    sys.exit(main())