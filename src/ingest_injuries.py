#!/usr/bin/env python3
"""
ingest_injuries.py — Ingesta de lesiones Liga MX desde ESPN API v2 (sin auth).

Fuente: https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/injuries
Mapea ESPN team.id ↔ SportMonks teams.id usando data/espn/team_mapping.json.
Inserta en tabla `player_injuries` (schema v2 ya existe, está vacía).

Uso:
    python3 src/ingest_injuries.py                    # ingesta activa
    python3 src/ingest_injuries.py --dry-run          # solo mostrar
    python3 src/ingest_injuries.py --team "América"   # solo 1 equipo

Estructura ESPN injury:
{
    "id": "...",
    "status": "Out" | "Doubtful" | "Questionable" | "Day-To-Day" | "Probable",
    "date": "2026-06-24T15:16Z",
    "athlete": {
        "firstName": "...", "lastName": "...",
        "displayName": "...", "shortName": "...",
        "position": {"name": "Midfielder", "abbreviation": "M"},
        "team": {"id": "232", "displayName": "Tigres UANL"}
    },
    "longComment": "...",
    "shortComment": "...",
    "type": {"name": "INJURY_STATUS_OUT", "description": "out"}
}
"""

import sys
import json
import sqlite3
import argparse
import requests
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/injuries"
ESPN_TEAM_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/teams"
MAPPING_PATH = PROJECT_ROOT / "data" / "espn" / "team_mapping.json"
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"

# Severidad → score de impacto. Out > Doubtful > Questionable > Day-To-Day > Probable.
SEVERITY_SCORE = {
    "Out": 1.00,
    "Doubtful": 0.75,
    "Questionable": 0.50,
    "Day-To-Day": 0.35,
    "Probable": 0.20,
    "Active": 0.0,
    "": 0.0,
}


def load_team_mapping():
    """Carga mapeo ESPN ID ↔ SportMonks ID."""
    with open(MAPPING_PATH) as f:
        data = json.load(f)
    # Devuelve {espn_id_str: sm_id_int}
    return {
        espn_id: info["sm_id"]
        for espn_id, info in data["teams"].items()
    }


def fetch_espn_injuries():
    """Pega a la API ESPN y devuelve lista cruda de lesiones."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    r = requests.get(ESPN_INJURIES_URL, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def parse_injury(entry, espn_to_sm):
    """
    Convierte una entrada ESPN a dict listo para insertar.
    Devuelve None si no se puede mapear el equipo.
    """
    athlete = entry.get("athlete", {})
    espn_team = athlete.get("team", {})
    espn_id = str(espn_team.get("id", ""))

    sm_id = espn_to_sm.get(espn_id)
    if not sm_id:
        return None  # Equipo sin match (ej. Mazatlán en pretemporada)

    status = entry.get("status", "")
    severity_score = SEVERITY_SCORE.get(status, 0.0)

    # Fechas
    date_str = entry.get("date", "")
    try:
        injury_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        injury_date = datetime.now(timezone.utc)

    position = athlete.get("position", {})
    return {
        "espn_id": entry.get("id"),
        "espn_team_id": espn_id,
        "sm_team_id": sm_id,
        "athlete_first": athlete.get("firstName", ""),
        "athlete_last": athlete.get("lastName", ""),
        "athlete_display": athlete.get("displayName", ""),
        "position": position.get("abbreviation", position.get("name", "")),
        "status": status,
        "severity_score": severity_score,
        "injury_date": injury_date.isoformat(),
        "long_comment": entry.get("longComment", "")[:500],
        "short_comment": entry.get("shortComment", "")[:200],
        "type_name": entry.get("type", {}).get("name", ""),
        "type_desc": entry.get("type", {}).get("description", ""),
    }


def match_player_in_db(conn, sm_team_id, athlete_display, athlete_last):
    """
    Busca el jugador SportMonks por fuzzy match (last name).
    Devuelve sm_player_id o None.
    """
    if not athlete_last:
        return None

    # Match exacto por last_name
    row = conn.execute(
        """
        SELECT p.id, p.full_name
        FROM players p
        WHERE p.last_name = ?
          AND JSON_EXTRACT(p.meta_json, '$.team_id') = ?
        LIMIT 1
        """,
        (athlete_last, sm_team_id),
    ).fetchone()
    if row:
        return row[0]

    # Match por contains (más permisivo)
    row = conn.execute(
        """
        SELECT p.id, p.full_name
        FROM players p
        WHERE p.last_name LIKE ?
          AND JSON_EXTRACT(p.meta_json, '$.team_id') = ?
        ORDER BY length(p.last_name) DESC
        LIMIT 1
        """,
        (f"%{athlete_last}%", sm_team_id),
    ).fetchone()
    if row:
        return row[0]

    return None


def get_current_season_id(conn, league_id=743):
    """Devuelve el season_id actual de Liga MX."""
    row = conn.execute(
        """
        SELECT id FROM seasons
        WHERE league_id = ? AND is_current = 1
        ORDER BY start_date DESC LIMIT 1
        """,
        (league_id,),
    ).fetchone()
    if row:
        return row[0]
    # Fallback: la más reciente
    row = conn.execute(
        """
        SELECT id FROM seasons
        WHERE league_id = ?
        ORDER BY start_date DESC LIMIT 1
        """,
        (league_id,),
    ).fetchone()
    return row[0] if row else None


def upsert_injury(conn, injury, sm_player_id, season_id):
    """
    Inserta o actualiza una lesión en player_injuries.
    Idempotencia: usa (espn_id) como clave lógica + UNIQUE implícito por meta_json.
    """
    meta = {
        "espn_id": injury["espn_id"],
        "source": "espn_api_v2",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "athlete_display": injury["athlete_display"],
        "position": injury["position"],
        "long_comment": injury["long_comment"],
        "short_comment": injury["short_comment"],
        "type_name": injury["type_name"],
        "type_desc": injury["type_desc"],
    }

    # ¿Existe ya?
    existing = conn.execute(
        "SELECT id FROM player_injuries WHERE meta_json LIKE ?",
        (f'%"espn_id": "{injury["espn_id"]}"%',),
    ).fetchone()

    if existing:
        # Actualizar (status puede haber cambiado)
        conn.execute(
            """
            UPDATE player_injuries
            SET player_id = ?, team_id = ?, season_id = ?,
                injury_type = ?, severity = ?, start_date = ?,
                meta_json = ?
            WHERE id = ?
            """,
            (
                sm_player_id,
                injury["sm_team_id"],
                season_id,
                injury["status"] or injury["type_desc"] or "Unknown",
                injury["status"],
                injury["injury_date"],
                json.dumps(meta),
                existing[0],
            ),
        )
        return "updated", existing[0]

    # Insertar nuevo
    cur = conn.execute(
        """
        INSERT INTO player_injuries
            (player_id, team_id, season_id, start_date, injury_type,
             severity, source, meta_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sm_player_id,
            injury["sm_team_id"],
            season_id,
            injury["injury_date"],
            injury["status"] or injury["type_desc"] or "Unknown",
            injury["status"],
            "espn_api_v2",
            json.dumps(meta),
        ),
    )
    return "inserted", cur.lastrowid


def main():
    parser = argparse.ArgumentParser(description="Ingerir lesiones Liga MX desde ESPN")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no insertar")
    parser.add_argument("--team", help="Filtrar por nombre de equipo (ej. 'América')")
    args = parser.parse_args()

    print(f"🏥 Ingesta de lesiones Liga MX — ESPN API v2")
    print(f"   {datetime.now(timezone.utc).isoformat()}")
    print()

    espn_to_sm = load_team_mapping()
    print(f"📋 Mapeo cargado: {len(espn_to_sm)} equipos ESPN ↔ SportMonks")
    print()

    raw = fetch_espn_injuries()
    raw_injuries = raw.get("injuries", [])
    print(f"📥 ESPN devolvió {len(raw_injuries)} equipos con lesiones")
    print()

    if not raw_injuries:
        print("⚠️  Sin lesiones activas reportadas por ESPN.")
        print("    Esto es normal en pretemporada. El script queda listo para agosto.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    season_id = get_current_season_id(conn)
    print(f"📅 Season actual Liga MX: {season_id}")
    print()

    if args.dry_run:
        conn.close()
        print("🔍 DRY RUN — solo mostrando estructura")
        for entry in raw_injuries:
            inj = parse_injury(entry, espn_to_sm)
            if not inj:
                continue
            if args.team and args.team.lower() not in inj["athlete_display"].lower():
                if args.team.lower() not in [t["espn_name"].lower() for t in json.loads(Path(MAPPING_PATH).read_text())["teams"].values()]:
                    continue
            print(f"  {inj['athlete_display']:30s} | {inj['status']:15s} | ESPN team {inj['espn_team_id']} → SM {inj['sm_team_id']}")
        return

    inserted = updated = skipped = 0
    team_breakdown = {}
    unmatched_players = []

    for entry in raw_injuries:
        inj = parse_injury(entry, espn_to_sm)
        if not inj:
            skipped += 1
            continue

        sm_player_id = match_player_in_db(conn, inj["sm_team_id"], inj["athlete_display"], inj["athlete_last"])
        if not sm_player_id:
            unmatched_players.append(inj)

        action, _ = upsert_injury(conn, inj, sm_player_id, season_id)
        if action == "inserted":
            inserted += 1
        else:
            updated += 1
        team_breakdown[inj["sm_team_id"]] = team_breakdown.get(inj["sm_team_id"], 0) + 1

    conn.commit()
    conn.close()

    print()
    print(f"✅ Resultado:")
    print(f"   Insertadas: {inserted}")
    print(f"   Actualizadas: {updated}")
    print(f"   Sin match (equipo no mapeado): {skipped}")
    print(f"   Jugadores no matcheados en BD: {len(unmatched_players)}")
    print()
    if team_breakdown:
        print(f"📊 Lesiones por equipo:")
        for sm_id, count in sorted(team_breakdown.items(), key=lambda x: -x[1]):
            print(f"   SM {sm_id:>6}  {count} lesionados")
    if unmatched_players:
        print(f"\n⚠️  Jugadores sin match en BD (revisar meta_json para agregar):")
        for u in unmatched_players[:10]:
            print(f"   - {u['athlete_display']} ({u['position']}, {u['status']}) team={u['sm_team_id']}")


if __name__ == "__main__":
    main()