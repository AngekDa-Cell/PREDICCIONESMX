#!/usr/bin/env python3
"""
refresh_fixtures_results.py — Refresca resultados (state + scores) de fixtures
ya finalizados desde SportMonks.

Para cada fixture con league_id=743, starting_at < now()-2h y state='NS',
llama a GET /fixtures/{id}?include=state,scores y actualiza home_score,
away_score y state en la tabla `fixtures`.

Uso:
  python3 scripts/refresh_fixtures_results.py            # modo real
  python3 scripts/refresh_fixtures_results.py --dry-run  # solo mostrar
  python3 scripts/refresh_fixtures_results.py --hours-back 4  # cutoff custom
"""

import sys
import json
import sqlite3
import argparse
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
LEAGUE_ID = 743


def get_fixtures_to_refresh(conn, hours_back: int) -> list:
    """Devuelve fixtures con state=NS que ya deberían estar finalizados."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute("""
        SELECT id, starting_at, state
        FROM fixtures
        WHERE league_id = ?
          AND starting_at < ?
          AND (state = 'NS' OR home_score IS NULL)
        ORDER BY starting_at
    """, (LEAGUE_ID, cutoff)).fetchall()
    return rows


def fetch_fixture(fixture_id: int, api_token: str, base_url: str) -> dict | None:
    """GET /fixtures/{id}?include=state,scores — uno por llamada (v3 no acepta comas)."""
    url = f"{base_url}/fixtures/{fixture_id}"
    out = {"id": fixture_id, "state": None, "scores": []}
    # Necesitamos tanto state como scores
    for inc in ("state", "scores"):
        try:
            r = requests.get(url, params={"api_token": api_token, "include": inc}, timeout=10)
            if r.status_code != 200:
                out.setdefault("errors", []).append(f"{inc}: HTTP {r.status_code} {r.text[:120]}")
                continue
            d = r.json().get("data", {})
            if inc == "state" and isinstance(d.get("state"), dict):
                out["state"] = d["state"].get("state")  # NS, FT, AOT, etc.
                out["result_info"] = d.get("result_info")
            if inc == "scores":
                out["scores"] = d.get("scores") or []
        except Exception as e:
            out.setdefault("errors", []).append(f"{inc}: {e}")
    return out


def extract_final_scores(scores: list, home_id: int, away_id: int) -> tuple[int | None, int | None]:
    """Extrae home_score y away_score del array `scores` (desc=CURRENT)."""
    home = away = None
    for sc in scores or []:
        desc = (sc.get("description") or "").upper()
        if desc != "CURRENT":
            continue
        goals = (sc.get("score") or {}).get("goals")
        if goals is None:
            continue
        # Determinar si es home o away
        participant = (sc.get("score") or {}).get("participant", "").lower()
        loc = (sc.get("location") or "").lower()
        pid = sc.get("participant_id")
        is_home = participant == "home" or loc == "home" or pid == home_id
        is_away = participant == "away" or loc == "away" or pid == away_id
        if is_home and home is None:
            home = goals
        elif is_away and away is None:
            away = goals
    return home, away


def update_fixture(conn, fid: int, state: str, home_score: int | None, away_score: int | None) -> bool:
    """UPDATE fixtures SET state, home_score, away_score WHERE id=?."""
    cur = conn.execute(
        "UPDATE fixtures SET state = ?, home_score = ?, away_score = ? WHERE id = ?",
        (state, home_score, away_score, fid),
    )
    return cur.rowcount > 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--hours-back", type=int, default=2, help="Cutoff en horas (default 2)")
    args = parser.parse_args()

    print(f"🔄 REFRESH FIXTURES RESULTS — Predictions_MX")
    print(f"   {datetime.now(timezone.utc).isoformat()}")
    print(f"   hours_back={args.hours_back} dry_run={args.dry_run}")
    print()

    # Cargar token
    from dotenv import load_dotenv
    import os
    load_dotenv(PROJECT_ROOT / ".env")
    api_token = os.environ.get("SPORTMONKS_API_TOKEN")
    base_url = os.environ.get("SPORTMONKS_BASE_URL", "https://api.sportmonks.com/v3/football")
    if not api_token:
        print("❌ SPORTMONKS_API_TOKEN no configurado")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))

    to_refresh = get_fixtures_to_refresh(conn, args.hours_back)
    print(f"📋 {len(to_refresh)} fixtures a refrescar (NS + starting_at < now()-{args.hours_back}h)")
    print()

    if not to_refresh:
        print("✅ Nada que refrescar")
        conn.close()
        return

    updated = 0
    errors = 0
    for fid, starting_at, state in to_refresh:
        print(f"  → Fixture {fid} (started {starting_at})…")

        if args.dry_run:
            print("    [dry-run]")
            continue

        data = fetch_fixture(fid, api_token, base_url)
        if data.get("errors"):
            print(f"    ❌ Errores API: {data['errors']}")
            errors += 1
            continue

        new_state = data.get("state") or "NS"
        if new_state == "NS":
            print(f"    ⏳ Aún NS según SportMonks (puede estar en juego o pendiente)")
            continue

        # Traer home/away team_id de la BD
        row = conn.execute("SELECT home_team_id, away_team_id FROM fixtures WHERE id = ?", (fid,)).fetchone()
        if not row:
            print(f"    ❌ Fixture {fid} no encontrado en BD")
            errors += 1
            continue
        home_id, away_id = row

        home_score, away_score = extract_final_scores(data.get("scores") or [], home_id, away_id)
        if home_score is None or away_score is None:
            print(f"    ⚠️ No se pudieron extraer scores finales: {data.get('scores')[:3]}")
            # Aun así actualizamos state si está disponible

        ok = update_fixture(conn, fid, new_state, home_score, away_score)
        if ok:
            result_info = data.get("result_info", "")
            print(f"    ✅ state={new_state} score={home_score}-{away_score} ({result_info})")
            updated += 1
        else:
            errors += 1

    if not args.dry_run:
        conn.commit()

    conn.close()

    print()
    print(f"📊 Resumen: {updated} actualizados, {errors} errores")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)