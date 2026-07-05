"""
ingest_attendance.py — Ingesta attendance histórica desde ESPN API para fixtures Liga MX.

ESPN API (gratis, sin auth, devuelve gzip-compressed JSON):
  https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates=YYYYMMDD-YYYYMMDD

Coverage por temporada:
- 2024 H2 (Apertura 2024): 100% (100/100)
- 2023 H1 (Clausura 2023): 96% (96/100)
- 2022 H2 (Apertura 2022): 52% (52/100)

Rate limit: ~3-5 req/s es seguro (no documentado).
Sleep entre requests: 0.3s

Uso:
  python3 src/ingest_attendance.py --dry-run
  python3 src/ingest_attendance.py --limit 100
  python3 src/ingest_attendance.py --start 2025-01-01 --end 2025-12-31
  python3 src/ingest_attendance.py  # full
"""
import argparse
import gzip
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Set, Tuple
import io

import requests

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
LEAGUE_ID = 743

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard"
REQUEST_TIMEOUT = 15
SLEEP_BETWEEN = 0.3  # 3.3 req/sec


# ─────────────────────────────────────────────────────────────────────────────
# ESPN team mapping → our team_id
# ─────────────────────────────────────────────────────────────────────────────

# ESPN usa "displayName" propio. Mapeo displayName → our team_id.
# Verificado en muestra de 2024-H2 (Apertura 2024).
ESPN_DISPLAYNAME_TO_TEAM_ID: Dict[str, int] = {
    "América": 2687,
    "Atlas": 680,
    "Atlético de San Luis": 15522,
    "Cruz Azul": 2626,
    "FC Juarez": 6335,
    "Guadalajara": 427,
    "León": 10836,
    "Mazatlán FC": 247689,
    "Monterrey": 2662,
    "Necaxa": 3951,
    "Pachuca": 10036,
    "Puebla": 3849,
    "Pumas UNAM": 2989,
    "Querétaro": 538,
    "Santos": 2844,                # ESPN "Santos" = nuestro "Santos Laguna"
    "Tigres UANL": 609,
    "Tijuana": 11023,
    "Toluca": 967,
}


# ─────────────────────────────────────────────────────────────────────────────
# ESPN FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_scoreboard(start_date: str, end_date: str, max_retries: int = 3) -> Optional[list]:
    """
    Fetch todos los eventos en un rango de fechas (1 año).

    Args:
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD

    Returns:
        Lista de eventos (dict) o None si falla
    """
    # ESPN usa YYYYMMDD sin guiones. weeks=1-60 + limit=500 da casi todos
    # los partidos del año (Apertura + Clausura + Liguilla).
    s = start_date.replace("-", "")
    e = end_date.replace("-", "")
    url = f"{ESPN_URL}?dates={s}-{e}&weeks=1-60&limit=500"

    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={
                "User-Agent": "Mozilla/5.0 (PredictionsMX/1.0)",
                "Accept-Encoding": "identity",  # evitar gzip encoding raro
            })
            r.raise_for_status()

            # ESPN a veces devuelve gzip aunque no lo pida
            data_bytes = r.content
            if data_bytes[:2] == b"\x1f\x8b":
                data_bytes = gzip.decompress(data_bytes)

            data = json.loads(data_bytes)
            return data.get("events", [])

        except Exception as ex:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"  ❌ fetch_scoreboard({start_date}, {end_date}) failed: {ex}", file=sys.stderr)
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE MATCHING
# ─────────────────────────────────────────────────────────────────────────────

def extract_teams(event: Dict) -> Optional[Tuple[str, str, int]]:
    """Extrae (home_abbr, away_abbr, attendance) de un evento ESPN.

    Retorna None si el evento no tiene estructura completa.
    """
    try:
        comp = event["competitions"][0]
        home = next(c for c in comp["competitors"] if c.get("homeAway") == "home")
        away = next(c for c in comp["competitors"] if c.get("homeAway") == "away")
        attendance = comp.get("attendance")
        if not attendance:
            return None
        home_dn = home["team"].get("displayName", "")
        away_dn = away["team"].get("displayName", "")
        return (home_dn, away_dn, int(attendance))
    except (KeyError, StopIteration, TypeError, ValueError):
        return None


def match_to_fixture(
    conn: sqlite3.Connection,
    home_dn: str,
    away_dn: str,
    event_date: str,
    tolerance_days: int = 1,
) -> Optional[int]:
    """Encuentra el fixture_id correspondiente a un partido ESPN.

    Args:
        conn: conexión a BD
        home_dn: displayName del equipo local (ESPN)
        away_dn: displayName del equipo visitante (ESPN)
        event_date: fecha del evento (ISO format)
        tolerance_days: tolerancia para match por fecha

    Returns:
        fixture_id o None
    """
    home_id = ESPN_DISPLAYNAME_TO_TEAM_ID.get(home_dn)
    away_id = ESPN_DISPLAYNAME_TO_TEAM_ID.get(away_dn)
    if not home_id or not away_id:
        return None

    # ESPN devuelve fecha en formato "2024-09-14T22:45Z"
    # Matchear con starting_at en BD (±1 día de tolerancia)
    event_date_only = event_date[:10]  # YYYY-MM-DD

    query = """
        SELECT id, starting_at FROM fixtures
        WHERE league_id = ?
          AND home_team_id = ?
          AND away_team_id = ?
          AND date(starting_at) BETWEEN ? AND ?
        ORDER BY ABS(julianday(starting_at) - julianday(?))
        LIMIT 1
    """
    from datetime import datetime, timedelta
    dt = datetime.fromisoformat(event_date_only)
    start = (dt - timedelta(days=tolerance_days)).strftime("%Y-%m-%d")
    end = (dt + timedelta(days=tolerance_days)).strftime("%Y-%m-%d")

    row = conn.execute(
        query,
        (LEAGUE_ID, home_id, away_id, start, end, event_date_only)
    ).fetchone()

    return row[0] if row else None


# ─────────────────────────────────────────────────────────────────────────────
# INGEST
# ─────────────────────────────────────────────────────────────────────────────

def get_date_ranges(start: str, end: str) -> list:
    """Divide el rango en chunks de 1 año natural (alineado a calendario)."""
    from datetime import datetime, timedelta
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    ranges = []
    # Empezar el 1 de enero del año de start
    cur = datetime(s.year, 1, 1)
    while cur <= e:
        # Fin del año natural o del rango, lo que sea menor
        year_end = datetime(cur.year, 12, 31)
        chunk_end = min(year_end, e)
        chunk_start = max(cur, s)
        if chunk_start <= chunk_end:
            ranges.append((chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        cur = datetime(cur.year + 1, 1, 1)
    return ranges


def ingest_attendance(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    """Ingesta attendance para todos los partidos en el rango."""
    stats = {
        "espn_events": 0,
        "matched": 0,
        "updated": 0,
        "unmatched_teams": 0,
        "unmatched_fixture": 0,
        "no_attendance": 0,
    }

    ranges = get_date_ranges(start_date, end_date)
    print(f"📊 Fetching attendance for {len(ranges)} chunks ({start_date} to {end_date})...")

    if dry_run:
        print("🔍 DRY RUN — no se escribirá a la BD")

    seen_fixtures: Set[int] = set()  # evitar updates duplicados en mismo chunk

    for chunk_idx, (cs, ce) in enumerate(ranges):
        print(f"\n📅 Chunk {chunk_idx+1}/{len(ranges)}: {cs} → {ce}")
        events = fetch_scoreboard(cs, ce)
        if events is None:
            print(f"  ❌ Failed to fetch chunk")
            continue

        stats["espn_events"] += len(events)
        print(f"  Found {len(events)} ESPN events")

        for event in events:
            teams = extract_teams(event)
            if teams is None:
                stats["no_attendance"] += 1
                continue

            home_dn, away_dn, attendance = teams

            fixture_id = match_to_fixture(conn, home_dn, away_dn, event["date"])
            if fixture_id is None:
                stats["unmatched_fixture"] += 1
                continue

            stats["matched"] += 1

            if dry_run:
                if stats["matched"] <= 5 or stats["matched"] % 50 == 0:
                    print(f"    Would update fixture {fixture_id}: {home_dn} vs {away_dn} → {attendance}")
                continue

            if fixture_id in seen_fixtures:
                continue
            seen_fixtures.add(fixture_id)

            try:
                conn.execute(
                    "UPDATE fixtures SET attendance = ? WHERE id = ? AND attendance IS NULL",
                    (attendance, fixture_id),
                )
                if conn.total_changes:
                    stats["updated"] += 1
            except sqlite3.Error as ex:
                print(f"  ❌ DB error: {ex}")

            if limit and stats["updated"] >= limit:
                print(f"\n🛑 Limit {limit} reached")
                conn.commit()
                return stats

        conn.commit()
        time.sleep(SLEEP_BETWEEN)

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest attendance from ESPN API")
    parser.add_argument("--start", default="2021-07-01", help="Fecha de inicio (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-12-31", help="Fecha de fin (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, help="Limitar a N updates")
    parser.add_argument("--dry-run", action="store_true", help="Solo contar, no escribir")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    stats = ingest_attendance(
        conn,
        start_date=args.start,
        end_date=args.end,
        dry_run=args.dry_run,
        limit=args.limit,
    )

    print("\n" + "=" * 60)
    print("📊 RESUMEN")
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k:25} {v}")
    print("=" * 60)

    if not args.dry_run:
        # Show coverage before/after
        row = conn.execute("""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN attendance IS NULL THEN 1 ELSE 0 END) AS sin,
              SUM(CASE WHEN attendance IS NOT NULL THEN 1 ELSE 0 END) AS con
            FROM fixtures WHERE league_id = ?
        """, (LEAGUE_ID,)).fetchone()
        if row:
            print(f"\n  Total fixtures Liga MX: {row['total']}")
            print(f"  Con attendance:         {row['con']} ({100*row['con']/row['total']:.1f}%)")
            print(f"  Sin attendance:         {row['sin']}")

    conn.close()


if __name__ == "__main__":
    main()