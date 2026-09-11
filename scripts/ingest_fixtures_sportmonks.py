#!/usr/bin/env python3
"""
ingest_fixtures_sportmonks.py — Ingiesta fixtures nuevos desde SportMonks (FIX 2026-09-10).

Bug original: `step_refresh_fixtures_sportmonks()` en full_pipeline.py solo
ENCONTRABA IDs nuevos pero NO los INSERTaba en la BD → pasos 3, 4, 5
corrían sin datos → predicciones siempre 0.

Estrategia:
1. SM fixtures/between con includes: participants;league;season;venue;state;scores
2. UPSERT primero FKs (league, season, venue, teams) — stubs mínimos si faltan
3. UPSERT fixtures con todos los campos
4. INSERT/UPDATE scores (CURRENT description) en fixture.home_score/away_score

Uso:
    python3 scripts/ingest_fixtures_sportmonks.py [--days 60] [--leagues 743,749]
"""

import sys
import sqlite3
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
LEAGUE_ID_DEFAULT = "743,749"  # Liga MX + Expansión


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--leagues", default=LEAGUE_ID_DEFAULT,
                        help="CSV league IDs (default: 743,749)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT))
    from src.config import SportMonksConfig
    from src.sportmonks_client import SportMonksClient

    if not DB_PATH.exists():
        print(f"❌ BD no existe: {DB_PATH}")
        return 1

    cfg = SportMonksConfig.from_env()
    client = SportMonksClient(cfg)

    # Rango: 7 días atrás hasta días adelante (incluye resultados recientes)
    start = (datetime.utcnow() - __import__("datetime").timedelta(days=7)).strftime("%Y-%m-%d")
    end = (datetime.utcnow() + __import__("datetime").timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"📥 SM fixtures {start} → {end}, leagues={args.leagues}")

    if args.dry_run:
        client.close()
        print("🔍 DRY-RUN")
        return 0

    # 1. Descargar fixtures con includes
    url = f"https://api.sportmonks.com/v3/football/fixtures/between/{start}/{end}"
    base_params = {
        "api_token": cfg.api_token,
        "leagues": args.leagues,
        "per_page": 50,
        "include": "participants;league;season;venue;state;scores",
    }

    all_fixtures = []
    page = 1
    while True:
        params = {**base_params, "page": page}
        r = client._request("fixtures/between/" + f"{start}/{end}", params)
        data = r.get("data", [])
        if not data:
            break
        all_fixtures.extend(data)
        if len(data) < 50:
            break
        page += 1
        time.sleep(0.1)  # rate-limit gentil

    print(f"   📊 {len(all_fixtures)} fixtures descargados")
    client.close()

    # 2. Conectar BD e UPSERT
    conn = sqlite3.connect(str(DB_PATH))
    inserted_fx = 0
    inserted_leagues = inserted_seasons = inserted_venues = inserted_teams = 0
    updated_scores = 0

    for fx in all_fixtures:
        fx_id = fx["id"]
        starting_at = fx.get("starting_at")
        league = fx.get("league") or {}
        season = fx.get("season") or {}
        venue = fx.get("venue") or {}
        state = (fx.get("state") or {}).get("state", "NS")

        # 2a. UPSERT league
        if league.get("id"):
            lid = league["id"]
            cur = conn.execute("SELECT 1 FROM leagues WHERE id=?", (lid,)).fetchone()
            if not cur:
                conn.execute(
                    "INSERT INTO leagues (id, name, country, tier, is_active, meta_json) "
                    "VALUES (?, ?, ?, ?, 1, '{}')",
                    (lid, league.get("name", ""), "Mexico",
                     "first" if lid == 743 else ("second" if lid == 749 else None)),
                )
                inserted_leagues += 1

        # 2b. UPSERT season
        if season.get("id"):
            sid = season["id"]
            cur = conn.execute("SELECT 1 FROM seasons WHERE id=?", (sid,)).fetchone()
            if not cur:
                conn.execute(
                    "INSERT OR IGNORE INTO seasons (id, league_id, name, is_current, meta_json) "
                    "VALUES (?, ?, ?, 1, '{}')",
                    (sid, league.get("id"), season.get("name", "")),
                )
                inserted_seasons += 1

        # 2c. UPSERT venue
        if venue.get("id"):
            vid = venue["id"]
            cur = conn.execute("SELECT 1 FROM venues WHERE id=?", (vid,)).fetchone()
            if not cur:
                conn.execute(
                    "INSERT OR IGNORE INTO venues (id, name, city, country, meta_json) "
                    "VALUES (?, ?, ?, 'Mexico', '{}')",
                    (vid, venue.get("name", ""), venue.get("city")),
                )
                inserted_venues += 1

        # 2d. UPSERT teams (participants)
        home_id = away_id = None
        for p in (fx.get("participants") or []):
            pid = p["id"]
            loc = (p.get("meta") or {}).get("location")
            cur = conn.execute("SELECT 1 FROM teams WHERE id=?", (pid,)).fetchone()
            if not cur:
                conn.execute(
                    "INSERT OR IGNORE INTO teams (id, name, country, meta_json) "
                    "VALUES (?, ?, 'Mexico', '{}')",
                    (pid, p.get("name", "")),
                )
                inserted_teams += 1
            if loc == "home":
                home_id = pid
            elif loc == "away":
                away_id = pid

        if not (home_id and away_id):
            continue

        # 2e. UPSERT fixture
        # home_score / away_score: parsear CURRENT scores
        home_score = away_score = None
        for s in (fx.get("scores") or []):
            if (s.get("description") or "").upper() != "CURRENT":
                continue
            pid = s.get("participant_id")
            goals = (s.get("score") or {}).get("goals")
            if pid == home_id:
                home_score = goals
            elif pid == away_id:
                away_score = goals

        try:
            conn.execute("""
                INSERT OR REPLACE INTO fixtures
                (id, season_id, league_id, venue_id, home_team_id, away_team_id,
                 starting_at, state, home_score, away_score, meta_json, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fx_id, season.get("id"), league.get("id"), venue.get("id"),
                home_id, away_id, starting_at, state,
                home_score, away_score,
                json.dumps({"name": fx.get("name", "")}),
                datetime.utcnow().isoformat() + "Z",
            ))
            inserted_fx += 1
            if home_score is not None:
                updated_scores += 1
        except sqlite3.IntegrityError as e:
            # FK failure — log y skip
            print(f"   ⚠️ FX {fx_id} FK error: {e}")
            continue

    conn.commit()
    conn.close()

    print()
    print(f"   ✅ Leagues nuevas: {inserted_leagues}")
    print(f"   ✅ Seasons nuevas: {inserted_seasons}")
    print(f"   ✅ Venues nuevos: {inserted_venues}")
    print(f"   ✅ Teams nuevos: {inserted_teams}")
    print(f"   ✅ Fixtures insert/updated: {inserted_fx} ({updated_scores} con score)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
