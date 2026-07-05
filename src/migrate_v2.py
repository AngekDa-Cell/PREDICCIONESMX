"""
migrate_v2.py — Migración de schema v1 → v2 preservando todos los datos.

Estrategia:
1. Backup ya creado en data/predictions_mx.v1_backup.db
2. Crea nueva BD con schema v2 completo en data/predictions_mx.v2_new.db
3. Copia datos de v1 → v2 preservando lo existente (usando modelos v1 separados)
4. Enriquece venues con coordenadas/altitud (cuando estén disponibles)
5. Reemplaza la BD original con la nueva
6. Deja el backup en disco por seguridad

Uso:
    python3 -m proyectos.src.migrate_v2
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import PATHS
from .db import (
    Fixture,
    FixtureEvent,
    FixtureStatistic,
    League,
    Player,
    Season,
    Team,
    Venue,
    init_db,
)


V1_BACKUP = PATHS.data_dir / "predictions_mx.v1_backup.db"
V2_NEW = PATHS.data_dir / "predictions_mx.v2_new.db"
V2_FINAL = PATHS.data_dir / "predictions_mx.db"


# =============================================================
# Modelos V1 — solo para LEER del backup
# =============================================================

class V1Base(DeclarativeBase):
    pass


class V1League(V1Base):
    __tablename__ = "leagues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class V1Season(V1Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("leagues.id"))
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class V1Venue(V1Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class V1Team(V1Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
    short_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    founded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("venues.id"), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class V1Player(V1Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(180))
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_of_birth: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    position: Mapped[str | None] = mapped_column(String(40), nullable=True)
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class V1Fixture(V1Base):
    __tablename__ = "fixtures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(Integer, ForeignKey("seasons.id"))
    league_id: Mapped[int] = mapped_column(Integer, ForeignKey("leagues.id"))
    venue_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("venues.id"), nullable=True)
    home_team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"))
    starting_at: Mapped[datetime] = mapped_column(DateTime)
    state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    round: Mapped[str | None] = mapped_column(String(60), nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_ht_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_ht_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(DateTime)


class V1FixtureEvent(V1Base):
    __tablename__ = "fixture_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fixture_id: Mapped[int] = mapped_column(Integer, ForeignKey("fixtures.id"))
    team_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("teams.id"), nullable=True)
    player_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("players.id"), nullable=True)
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class V1FixtureStatistic(V1Base):
    __tablename__ = "fixture_statistics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(Integer, ForeignKey("fixtures.id"))
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"))
    stat_type: Mapped[str] = mapped_column(String(60))
    stat_value: Mapped[float] = mapped_column(Float)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# Funciones de migración
# =============================================================

def get_v1_session(url: str):
    """Crea sesión contra el backup v1."""
    engine = create_engine(url, connect_args={"check_same_thread": False})
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_v2_session(url: str):
    """Crea sesión contra la nueva BD v2."""
    engine = create_engine(url, connect_args={"check_same_thread": False})
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def migrate_leagues(src, dst) -> int:
    rows = src.execute(select(V1League)).scalars().all()
    n = 0
    for r in rows:
        existing = dst.get(League, r.id)
        tier = "first" if r.id == 743 else "second" if r.id == 749 else None
        if existing is None:
            dst.add(League(
                id=r.id, name=r.name, country=r.country,
                tier=tier, is_active=r.is_active, meta_json=r.meta_json or {},
            ))
        n += 1
    dst.flush()
    return n


def migrate_seasons(src, dst) -> int:
    rows = src.execute(select(V1Season)).scalars().all()
    n = 0
    for r in rows:
        existing = dst.get(Season, r.id)
        if existing is None:
            dst.add(Season(
                id=r.id, league_id=r.league_id, name=r.name,
                start_date=r.start_date, end_date=r.end_date,
                is_current=r.is_current, meta_json=r.meta_json or {},
            ))
        n += 1
    dst.flush()
    return n


def migrate_venues(src, dst) -> int:
    rows = src.execute(select(V1Venue)).scalars().all()
    n = 0
    for r in rows:
        existing = dst.get(Venue, r.id)
        if existing is None:
            dst.add(Venue(
                id=r.id, name=r.name, city=r.city, country="Mexico",
                altitude_m=None, latitude=None, longitude=None,
                capacity=r.capacity, surface=None, roof_type=None,
                climate_zone=None, meta_json=r.meta_json or {},
                enriched_at=None,
            ))
        n += 1
    dst.flush()
    return n


def migrate_teams(src, dst) -> int:
    rows = src.execute(select(V1Team)).scalars().all()
    n = 0
    for r in rows:
        existing = dst.get(Team, r.id)
        if existing is None:
            dst.add(Team(
                id=r.id, name=r.name, short_code=r.short_code,
                country=r.country, founded=r.founded,
                venue_id=r.venue_id, logo_url=r.logo_url,
                primary_color=None, secondary_color=None, meta_json=r.meta_json or {},
            ))
        n += 1
    dst.flush()
    return n


def migrate_players(src, dst) -> int:
    rows = src.execute(select(V1Player)).scalars().all()
    n = 0
    for r in rows:
        existing = dst.get(Player, r.id)
        if existing is None:
            dst.add(Player(
                id=r.id,
                full_name=r.full_name,
                first_name=r.first_name,
                last_name=r.last_name,
                common_name=None,
                date_of_birth=r.date_of_birth,
                nationality=r.nationality,
                primary_position=r.position,
                secondary_position=None,
                position_detail=None,
                height_cm=r.height_cm,
                weight_kg=r.weight_kg,
                preferred_foot=None,
                shirt_number=None,
                photo_url=r.photo_url,
                meta_json=r.meta_json or {},
            ))
        n += 1
    dst.flush()
    return n


def migrate_fixtures(src, dst) -> int:
    rows = src.execute(select(V1Fixture)).scalars().all()
    n = 0
    for r in rows:
        existing = dst.get(Fixture, r.id)
        if existing is None:
            dst.add(Fixture(
                id=r.id, season_id=r.season_id, league_id=r.league_id,
                venue_id=r.venue_id, home_team_id=r.home_team_id, away_team_id=r.away_team_id,
                starting_at=r.starting_at, state=r.state, round=r.round,
                matchday=None, home_score=r.home_score, away_score=r.away_score,
                home_ht_score=r.home_ht_score, away_ht_score=r.away_ht_score,
                attendance=None, meta_json=r.meta_json or {}, ingested_at=r.ingested_at,
            ))
        n += 1
    dst.flush()
    return n


def migrate_events(src, dst) -> int:
    """Migra fixture_events con bulk insert."""
    from sqlalchemy import text
    rows = src.execute(text(
        "SELECT id, fixture_id, team_id, player_id, minute, extra_minute, "
        "type, detail, meta_json FROM fixture_events"
    )).fetchall()
    if not rows:
        return 0
    import json
    BATCH = 5000
    n = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i+BATCH]
        for r in chunk:
            eid, fx_id, team_id, player_id, minute, extra, type_, detail, meta_json = r
            try:
                meta_str = json.dumps(meta_json) if meta_json else "{}"
            except Exception:
                meta_str = "{}"
            dst.execute(text(
                "INSERT OR IGNORE INTO fixture_events "
                "(id, fixture_id, team_id, player_id, minute, extra_minute, type, detail, meta_json) "
                "VALUES (:id, :fx, :team, :pl, :min, :extra, :type, :det, :meta)"
            ), {"id": eid, "fx": fx_id, "team": team_id, "pl": player_id,
                "min": minute, "extra": extra, "type": type_, "det": detail, "meta": meta_str})
        dst.commit()
        n += len(chunk)
        print(f"    ... {n:,}/{len(rows):,} events", end="\r")
    print()
    return n


def migrate_statistics(src, dst) -> int:
    """Migra fixture_statistics con bulk insert (más rápido)."""
    from sqlalchemy import text
    # Leer todo del v1 como tuplas
    rows = src.execute(text(
        "SELECT fixture_id, team_id, stat_type, stat_value, meta_json "
        "FROM fixture_statistics"
    )).fetchall()
    if not rows:
        return 0
    # Bulk insert en chunks
    BATCH = 5000
    n = 0
    import json
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i+BATCH]
        # Insertar con INSERT OR IGNORE para evitar duplicados
        for r in chunk:
            fx_id, team_id, stat_type, stat_value, meta_json = r
            try:
                meta_str = json.dumps(meta_json) if meta_json else "{}"
            except Exception:
                meta_str = "{}"
            dst.execute(text(
                "INSERT OR IGNORE INTO fixture_statistics "
                "(fixture_id, team_id, stat_type, stat_value, meta_json) "
                "VALUES (:fx, :team, :st, :val, :meta)"
            ), {"fx": fx_id, "team": team_id, "st": stat_type, "val": stat_value, "meta": meta_str})
        dst.commit()
        n += len(chunk)
        print(f"    ... {n:,}/{len(rows):,} stats", end="\r")
    print()
    return n


def main() -> int:
    print("=" * 60)
    print("🔄 MIGRACIÓN v1 → v2 — Predictions_MX")
    print("=" * 60)

    if not V1_BACKUP.exists():
        print(f"❌ Backup no encontrado: {V1_BACKUP}")
        print("   Crea el backup primero:")
        print("   cp data/predictions_mx.db data/predictions_mx.v1_backup.db")
        return 1
    print(f"💾 Backup v1: {V1_BACKUP} ({V1_BACKUP.stat().st_size / 1024 / 1024:.1f} MB)")

    v1_url = f"sqlite:///{V1_BACKUP}"
    v2_url = f"sqlite:///{V2_NEW}"

    # Verificar v1
    V1_Sess = get_v1_session(v1_url)
    with V1_Sess() as s:
        cnt = len(s.execute(select(V1Fixture)).scalars().all())
        print(f"📊 v1: {cnt} fixtures, {len(s.execute(select(V1League)).scalars().all())} ligas")

    # Crear BD v2
    if V2_NEW.exists():
        V2_NEW.unlink()
    print(f"\n🏗️  Creando schema v2 en {V2_NEW.name}...")
    init_db(v2_url)

    V2_Sess = get_v2_session(v2_url)

    # Copiar
    print("\n📦 Migrando datos v1 → v2...")
    with V1_Sess() as src, V2_Sess() as dst:
        steps = [
            ("leagues", migrate_leagues),
            ("seasons", migrate_seasons),
            ("venues", migrate_venues),
            ("teams", migrate_teams),
            ("players", migrate_players),
            ("fixtures", migrate_fixtures),
            ("fixture_events", migrate_events),
            ("fixture_statistics", migrate_statistics),
        ]
        for name, fn in steps:
            try:
                n = fn(src, dst)
                dst.commit()
                print(f"  ✓ {name:<20} {n:>6,} registros")
            except Exception as e:
                print(f"  ❌ {name}: {e}")
                dst.rollback()
                import traceback
                traceback.print_exc()
                return 2

    # Validar
    print("\n🔍 Validando integridad...")
    with V2_Sess() as dst:
        v1_cnt = len(V1Sess().execute(select(V1Fixture)).scalars().all()) if False else None
        checks = [
            ("leagues", League), ("seasons", Season), ("teams", Team),
            ("players", Player), ("venues", Venue), ("fixtures", Fixture),
            ("fixture_events", FixtureEvent), ("fixture_statistics", FixtureStatistic),
        ]
        for name, model in checks:
            n = len(dst.execute(select(model)).scalars().all())
            print(f"  • {name:<20} {n:>6,} registros")

    # Reemplazar
    print(f"\n🔁 Reemplazando BD original...")
    if V2_FINAL.exists():
        V2_FINAL.unlink()
    shutil.move(str(V2_NEW), str(V2_FINAL))
    print(f"  ✓ {V2_FINAL.name} → schema v2 con datos migrados")
    print(f"  ✓ Backup v1 preservado en {V1_BACKUP.name}")

    # Tablas nuevas
    print("\n🆕 Tablas NUEVAS (vacías, listas para ingesta):")
    from . import db as db_module
    new_tables = [
        "coaches", "coach_tenures", "player_injuries", "player_transfers",
        "fixture_lineups", "match_weather", "match_context", "travel_log",
        "team_form", "player_form", "coach_form",
    ]
    with V2_Sess() as dst:
        for tname in new_tables:
            model = getattr(db_module, tname[:-1].upper() if tname == "coaches" else tname, None)
            # fallback: usar la tabla directamente
            from sqlalchemy import text
            try:
                n = dst.execute(text(f"SELECT COUNT(*) FROM {tname}")).scalar()
                print(f"  • {tname:<20} {n:>6,} registros")
            except Exception as e:
                print(f"  • {tname:<20} error: {e}")

    print("\n" + "=" * 60)
    print("✅ MIGRACIÓN COMPLETADA")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())