"""
ingest_weather.py — Ingesta weather histórica desde Open-Meteo para fixtures Liga MX.

Open-Meteo Archive API (gratis, sin API key):
  https://archive-api.open-meteo.com/v1/archive

Variables obtenidas por fixture:
- temperature_2m_max (°C)
- temperature_2m_min (°C)
- precipitation_sum (mm)
- wind_speed_10m_max (km/h)
- wind_direction_10m_dominant (°)
- relative_humidity_2m_max (%)

Derivadas:
- feels_like_c = (max + min) / 2
- conditions = categorización simple (seco/lluvioso/tormenta)
- cloud_cover_pct = null (Open-Meteo archive no tiene histórico diario directo)

Uso:
  python3 src/ingest_weather.py --dry-run
  python3 src/ingest_weather.py --limit 100
  python3 src/ingest_weather.py --start 2025-01-01 --end 2025-12-31
  python3 src/ingest_weather.py  # full
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import requests

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
LEAGUE_ID = 743

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
REQUEST_TIMEOUT = 15  # segundos
SLEEP_BETWEEN = 0.1   # 10 req/sec


# ─────────────────────────────────────────────────────────────────────────────
# OPEN-METEO FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_weather(lat: float, lon: float, date_str: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """
    Fetch weather de Open-Meteo Archive para una fecha y ubicación.

    Args:
        lat: latitud del venue
        lon: longitud del venue
        date_str: fecha en formato YYYY-MM-DD
        max_retries: número de reintentos en caso de fallo

    Returns:
        Dict con weather data o None si falla
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date_str,
        "end_date": date_str,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "wind_speed_10m_max,wind_direction_10m_dominant,relative_humidity_2m_max",
        "timezone": "America/Mexico_City",
    }

    for attempt in range(max_retries):
        try:
            r = requests.get(OPEN_METEO_URL, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()

            if "daily" not in data or not data["daily"].get("time"):
                return None

            daily = data["daily"]
            return {
                "temperature_max": daily["temperature_2m_max"][0] if daily.get("temperature_2m_max") else None,
                "temperature_min": daily["temperature_2m_min"][0] if daily.get("temperature_2m_min") else None,
                "precipitation": daily["precipitation_sum"][0] if daily.get("precipitation_sum") else None,
                "wind_speed": daily["wind_speed_10m_max"][0] if daily.get("wind_speed_10m_max") else None,
                "wind_direction": daily["wind_direction_10m_dominant"][0] if daily.get("wind_direction_10m_dominant") else None,
                "humidity": daily["relative_humidity_2m_max"][0] if daily.get("relative_humidity_2m_max") else None,
            }
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # backoff exponencial
            else:
                print(f"  ❌ Failed after {max_retries} attempts: {e}")
                return None
        except (KeyError, IndexError, ValueError) as e:
            print(f"  ⚠️ Data parse error: {e}")
            return None

    return None


def categorize_conditions(precipitation_mm: Optional[float], humidity_pct: Optional[int]) -> str:
    """Categoriza las condiciones del clima."""
    if precipitation_mm is None:
        return "unknown"

    if precipitation_mm >= 10:
        return "tormenta"
    elif precipitation_mm >= 2:
        return "lluvioso"
    elif precipitation_mm >= 0.5:
        return "llovizna"
    elif humidity_pct and humidity_pct >= 80:
        return "humedo"
    else:
        return "seco"


# ─────────────────────────────────────────────────────────────────────────────
# INGEST
# ─────────────────────────────────────────────────────────────────────────────

def get_fixtures_to_ingest(
    conn: sqlite3.Connection,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> list:
    """Obtiene fixtures históricos sin weather."""
    query = """
        SELECT f.id, f.starting_at, v.latitude, v.longitude, v.name
        FROM fixtures f
        JOIN venues v ON v.id = f.venue_id
        WHERE f.league_id = ?
          AND v.latitude IS NOT NULL
          AND v.longitude IS NOT NULL
          AND f.starting_at < datetime('now')
          AND NOT EXISTS (SELECT 1 FROM match_weather WHERE fixture_id = f.id)
    """
    params = [LEAGUE_ID]

    if start_date:
        query += " AND f.starting_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND f.starting_at < ?"
        params.append(end_date)

    query += " ORDER BY f.starting_at"

    if limit:
        query += " LIMIT ?"
        params.append(int(limit))

    return conn.execute(query, params).fetchall()


def ingest_weather(
    conn: sqlite3.Connection,
    fixtures: list,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Ingesta weather para una lista de fixtures."""
    stats = {"success": 0, "failed": 0, "skipped": 0}

    print(f"📊 Ingesting weather for {len(fixtures)} fixtures...")
    if dry_run:
        print("🔍 DRY RUN — no se escribirá a la BD")

    for i, (fid, starting_at, lat, lon, venue_name) in enumerate(fixtures):
        date_str = starting_at.split(" ")[0]  # YYYY-MM-DD

        if dry_run:
            if i < 5 or i % 100 == 0:
                print(f"  [{i+1}/{len(fixtures)}] Would fetch: {venue_name} @ {date_str}")
            stats["success"] += 1
            continue

        # Fetch weather
        w = fetch_weather(lat, lon, date_str)
        if w is None or w.get("temperature_max") is None:
            stats["failed"] += 1
            continue

        # Calcular derivadas
        feels_like = (w["temperature_max"] + w["temperature_min"]) / 2 if w["temperature_min"] else None
        conditions = categorize_conditions(w["precipitation"], int(w["humidity"]) if w["humidity"] else None)

        # Insertar en BD
        try:
            conn.execute("""
                INSERT OR REPLACE INTO match_weather
                (fixture_id, temperature_c, feels_like_c, humidity_pct, wind_kph,
                 wind_direction, precipitation_mm, conditions, cloud_cover_pct,
                 data_source, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fid,
                w["temperature_max"],
                feels_like,
                int(w["humidity"]) if w["humidity"] else None,
                w["wind_speed"],
                int(w["wind_direction"]) if w["wind_direction"] is not None else None,
                w["precipitation"],
                conditions,
                None,  # Open-Meteo archive no da cloud cover diario histórico directamente
                "open-meteo-archive",
                datetime.now().isoformat(),
            ))
            conn.commit()
            stats["success"] += 1
        except sqlite3.Error as e:
            print(f"  ❌ DB error for fixture {fid}: {e}")
            stats["failed"] += 1
            continue

        # Progress
        if stats["success"] % 100 == 0:
            print(f"  ✅ {stats['success']}/{len(fixtures)} ingested...")
        if (i + 1) % 500 == 0:
            print(f"  ⏳ Progress: {i+1}/{len(fixtures)}...")

        time.sleep(SLEEP_BETWEEN)

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest weather data from Open-Meteo")
    parser.add_argument("--start", help="Fecha de inicio (YYYY-MM-DD)")
    parser.add_argument("--end", help="Fecha de fin (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, help="Limitar a N fixtures")
    parser.add_argument("--dry-run", action="store_true", help="Solo contar, no escribir")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"❌ BD no encontrada: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    fixtures = get_fixtures_to_ingest(conn, args.start, args.end, args.limit)
    print(f"📊 {len(fixtures)} fixtures sin weather")

    if not fixtures:
        print("✅ Todos los fixtures ya tienen weather")
        conn.close()
        return

    if args.dry_run:
        print("\n🔍 Muestra de los primeros 5:")
        for f in fixtures[:5]:
            print(f"  - Fixture {f[0]} @ {f[1]} ({f[4]})")
        print(f"\nTotal a ingestar: {len(fixtures)}")
        print(f"Tiempo estimado: ~{len(fixtures) * 0.2 / 60:.1f} minutos")
        conn.close()
        return

    print()
    start_time = time.time()
    stats = ingest_weather(conn, fixtures, dry_run=False)
    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"📊 RESUMEN:")
    print(f"  ✅ Exitosos:  {stats['success']}")
    print(f"  ❌ Fallidos:  {stats['failed']}")
    print(f"  ⏭️  Saltados:  {stats['skipped']}")
    print(f"  ⏱️  Tiempo:    {elapsed:.1f}s ({elapsed/len(fixtures):.2f}s/fixture)")
    print(f"{'='*60}")

    # Verificar
    total = conn.execute("SELECT COUNT(*) FROM match_weather").fetchone()[0]
    print(f"\n📊 Total match_weather en BD: {total}")

    conn.close()


if __name__ == "__main__":
    main()