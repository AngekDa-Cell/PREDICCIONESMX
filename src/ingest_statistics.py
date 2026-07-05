"""
ingest_statistics.py — Ingiesta SOLO las statistics de fixtures existentes.

Estrategia:
1. Una llamada inicial al primer fixture con include=fixtures.statistics.type
   (per_page=1) para construir el catálogo completo de type_id → code.
2. Llamadas por temporada con include=fixtures.statistics (sin .type) para
   obtener las stats rápido, y mapeamos type_id → code localmente.

Uso:
    python3 -m proyectos.src.ingest_statistics
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import PATHS, SportMonksConfig
from .db import (
    Fixture,
    FixtureStatistic,
    Season,
    get_session,
)
from .logging_setup import setup_logging
from .sportmonks_client import SportMonksClient, SportMonksError


CACHE_FILE = PATHS.data_dir / "stat_type_mapping.json"


def build_stat_type_mapping(client: SportMonksClient, sample_season_id: int) -> dict[int, dict]:
    """Hace una llamada al primer fixture de una temporada y devuelve el mapeo
    completo type_id → {code, name, developer_name}.
    
    Cachea el resultado en disco para no repetir la llamada.
    """
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                raw = json.load(f)
                return {int(k): v for k, v in raw.items()}
        except Exception:
            pass

    print("🔨 Construyendo catálogo de stat types (1 call)...")
    r = client._request(f"seasons/{sample_season_id}", {
        "include": "fixtures.statistics.type",
        "per_page": 1,  # solo 1 fixture para sacar el catálogo
    })
    data = r.get("data", {})
    fixtures = data.get("fixtures", [])
    mapping: dict[int, dict] = {}
    for f in fixtures:
        for s in (f.get("statistics") or []):
            t = s.get("type") or {}
            tid = s.get("type_id")
            if tid and t:
                mapping[tid] = {
                    "code": t.get("code"),
                    "name": t.get("name"),
                    "developer_name": t.get("developer_name"),
                }
    # Cachear
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({str(k): v for k, v in mapping.items()}, f, indent=2, ensure_ascii=False)
    print(f"  ✓ {len(mapping)} tipos catalogados → {CACHE_FILE.name}")
    return mapping


def upsert_statistics(
    session: Session,
    fixture: Fixture,
    stats: list[dict],
    type_mapping: dict[int, dict],
    existing_cache: dict[tuple, FixtureStatistic] | None = None,
) -> int:
    """Inserta/actualiza stats por equipo de un fixture.
    
    Para máximo rendimiento, pasa `existing_cache` con un dict
    {(fixture_id, team_id, stat_type) → FixtureStatistic} pre-cargado.
    Así evitamos queries por cada stat individual.
    """
    n = 0
    for s in stats:
        type_id = s.get("type_id")
        if not type_id:
            continue
        info = type_mapping.get(type_id)
        if not info:
            stat_type = f"unknown_type_{type_id}"
        else:
            stat_type = info.get("code") or f"unknown_type_{type_id}"
        team_id = s.get("participant_id")
        if not team_id:
            continue
        value = s.get("data", {}).get("value") if isinstance(s.get("data"), dict) else s.get("value")
        if value is None:
            continue
        try:
            value_f = float(value)
        except (TypeError, ValueError):
            continue

        key = (fixture.id, team_id, stat_type)
        if existing_cache is not None and key in existing_cache:
            existing = existing_cache[key]
            existing.stat_value = value_f
            existing.meta_json = s
        else:
            new_obj = FixtureStatistic(
                fixture_id=fixture.id,
                team_id=team_id,
                stat_type=stat_type,
                stat_value=value_f,
                meta_json=s,
            )
            session.add(new_obj)
            if existing_cache is not None:
                existing_cache[key] = new_obj
            n += 1
    return n


def preload_existing_stats(session: Session, fixture_ids: list[int]) -> dict[tuple, FixtureStatistic]:
    """Carga todas las FixtureStatistic de los fixtures dados en un dict."""
    rows = session.query(FixtureStatistic).filter(
        FixtureStatistic.fixture_id.in_(fixture_ids)
    ).all()
    cache: dict[tuple, FixtureStatistic] = {}
    for r in rows:
        cache[(r.fixture_id, r.team_id, r.stat_type)] = r
    return cache


def main() -> int:
    setup_logging("INFO")

    cfg = SportMonksConfig.from_env()
    Session = get_session()

    with Session() as session:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        seasons = session.execute(
            select(Season)
            .where(Season.end_date < now)
            .order_by(Season.league_id, Season.start_date.desc())
        ).scalars().all()
        by_league: dict[int, list[Season]] = {}
        for s in seasons:
            by_league.setdefault(s.league_id, []).append(s)
        target: list[Season] = []
        for lid in sorted(by_league):
            target.extend(by_league[lid][:5])

        print(f"🎯 {len(target)} temporadas objetivo (5 por liga):")
        for s in target:
            print(f"   • L{s.league_id} | {s.id} | {s.name}")
        print()

    if not target:
        print("❌ Sin temporadas objetivo")
        return 1

    sample_season_id = target[0].id

    total_stats = 0
    with SportMonksClient(cfg) as client, Session() as session:
        # 1. Construir/recuperar catálogo de types
        type_mapping = build_stat_type_mapping(client, sample_season_id)
        print(f"  📚 Catálogo: {len(type_mapping)} tipos\n")

        # 2. Ingiesta por temporada
        for s in target:
            season = session.get(Season, s.id)
            if not season:
                continue
            print(f"→ Liga {s.league_id} | {s.name} (id={s.id})")
            try:
                fixtures = client.get_fixtures_by_season(s.id, include="statistics")
            except SportMonksError as e:
                print(f"  ⚠️  Error: {e}")
                continue
            # Pre-cargar stats existentes en memoria para evitar queries por stat
            fixture_ids = [f["id"] for f in fixtures]
            existing_cache = preload_existing_stats(session, fixture_ids)
            added = 0
            for f in fixtures:
                fid = f.get("id")
                fixture = session.get(Fixture, fid)
                if not fixture:
                    continue
                stats = f.get("statistics") or []
                added += upsert_statistics(session, fixture, stats, type_mapping, existing_cache)
            session.commit()
            print(f"  ✓ {len(fixtures)} fixtures | {added} stats nuevas (cache: {len(existing_cache)} existentes)")
            total_stats += added

    print()
    print("=" * 50)
    print(f"📊 Total stats insertadas/actualizadas: {total_stats}")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())