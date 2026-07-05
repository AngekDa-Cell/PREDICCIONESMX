"""
db.py — Schema v2 completo de Predictions_MX.

19 tablas (8 mejoradas + 11 nuevas) para análisis profundo de Liga MX:
- Captura todo lo scrapeable (SportMonks)
- Estructura para enriquecimiento manual (psicología, contexto)
- Calcula features derivadas (forms, fatiga, viaje)

Inicialización:
    python3 -m proyectos.src.init_db

Migración desde v1 (preserva datos):
    python3 -m proyectos.src.migrate_v2
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import DATABASE_URL, PATHS


# =============================================================
# Base
# =============================================================

class Base(DeclarativeBase):
    """Base declarativa de SQLAlchemy."""
    pass


# =============================================================
# 1. LEAGUES (mejorada)
# =============================================================

class League(Base):
    """Liga: Liga MX, Liga de Expansión MX, etc."""
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks id
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(80), nullable=False, default="Mexico")
    tier: Mapped[str | None] = mapped_column(String(40), nullable=True)  # "first", "second"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# 2. SEASONS
# =============================================================

class Season(Base):
    """Temporada (Apertura 2023, Clausura 2024, etc.)."""
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks id
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("league_id", "name", name="uq_season_league_name"),
    )


# =============================================================
# 3. VENUES (MEJORADA — altitud, coords, clima)
# =============================================================

class Venue(Base):
    """Estadio / sede con datos completos de ubicación."""
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True, default="Mexico")
    # Ubicación geográfica
    altitude_m: Mapped[int | None] = mapped_column(Integer, nullable=True)  # msnm
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Características físicas
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(40), nullable=True)  # grass, artificial, hybrid
    roof_type: Mapped[str | None] = mapped_column(String(40), nullable=True)  # open, retractable, fixed
    climate_zone: Mapped[str | None] = mapped_column(String(40), nullable=True)  # arid, temperate, tropical
    # Meta
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# =============================================================
# 4. TEAMS (mejorada — colores, etc.)
# =============================================================

class Team(Base):
    """Equipo con detalles visuales y de marca."""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks id
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    short_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    founded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    secondary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# 5. PLAYERS (MEJORADA — preferred_foot, posiciones)
# =============================================================

class Player(Base):
    """Jugador con detalles físicos y técnicos completos."""
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks id
    full_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    common_name: Mapped[str | None] = mapped_column(String(120), nullable=True)  # Alias / apodo
    date_of_birth: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Posiciones
    primary_position: Mapped[str | None] = mapped_column(String(40), nullable=True)  # GK, DF, MF, FW
    secondary_position: Mapped[str | None] = mapped_column(String(40), nullable=True)
    position_detail: Mapped[str | None] = mapped_column(String(40), nullable=True)  # CB, LB, CDM, etc.
    # Físico
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_foot: Mapped[str | None] = mapped_column(String(10), nullable=True)  # left, right, both
    # Identidad
    shirt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# 6. COACHES (NUEVO)
# =============================================================

class Coach(Base):
    """Director Técnico / Entrenador."""
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks id
    full_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    common_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_of_birth: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Estilo táctico (manual o scrapeable de SportMonks)
    tactical_style: Mapped[str | None] = mapped_column(String(40), nullable=True)  # offensive, defensive, possession, counter
    formation_preference: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 4-4-2, 4-3-3
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# 7. COACH TENURES (NUEVO — historial DT x equipo)
# =============================================================

class CoachTenure(Base):
    """Periodo en que un DT dirigió a un equipo."""
    __tablename__ = "coach_tenures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False, index=True)
    start_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    games_managed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draws: Mapped[int | None] = mapped_column(Integer, nullable=True)
    losses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("coach_id", "team_id", "season_id", name="uq_coach_team_season"),
    )


# =============================================================
# 8. PLAYER INJURIES (NUEVO)
# =============================================================

class PlayerInjury(Base):
    """Historial de lesiones de un jugador."""
    __tablename__ = "player_injuries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)  # equipo cuando se lesionó
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    injury_type: Mapped[str | None] = mapped_column(String(80), nullable=True)  # muscle, ligament, fracture
    body_part: Mapped[str | None] = mapped_column(String(60), nullable=True)  # knee, hamstring, ankle
    games_missed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)  # minor, moderate, severe
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)  # sportmonks, manual
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# 9. PLAYER TRANSFERS (NUEVO)
# =============================================================

class PlayerTransfer(Base):
    """Transferencia de un jugador entre equipos."""
    __tablename__ = "player_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)
    from_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    to_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    transfer_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    fee_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    transfer_type: Mapped[str | None] = mapped_column(String(40), nullable=True)  # permanent, loan, free
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# 10. FIXTURES (mejorada — attendance, jornada)
# =============================================================

class Fixture(Base):
    """Partido con todos los datos."""
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks id
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False, index=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), nullable=False, index=True)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    starting_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    round: Mapped[str | None] = mapped_column(String(60), nullable=True)
    matchday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_ht_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_ht_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attendance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_fixture_season_home", "season_id", "home_team_id"),
        Index("ix_fixture_season_away", "season_id", "away_team_id"),
        Index("ix_fixture_starting", "starting_at"),
    )


# =============================================================
# 11. FIXTURE EVENTS
# =============================================================

class FixtureEvent(Base):
    """Evento de un partido (gol, tarjeta, sustitución)."""
    __tablename__ = "fixture_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks id
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# 12. FIXTURE STATISTICS
# =============================================================

class FixtureStatistic(Base):
    """Estadísticas por partido (posesión, tiros, córners, etc.)."""
    __tablename__ = "fixture_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    stat_type: Mapped[str] = mapped_column(String(60), nullable=False)
    stat_value: Mapped[float] = mapped_column(Float, nullable=False)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("fixture_id", "team_id", "stat_type", name="uq_fixture_team_stat"),
    )


# =============================================================
# 13. FIXTURE LINEUPS (NUEVO — alineaciones con rating)
# =============================================================

class FixtureLineup(Base):
    """Alineación de un jugador en un partido específico."""
    __tablename__ = "fixture_lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    # Posición y rol
    is_starter: Mapped[bool] = mapped_column(Boolean, default=True)
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)
    position_group: Mapped[str | None] = mapped_column(String(20), nullable=True)  # GK, DEF, MID, FWD
    position_detail: Mapped[str | None] = mapped_column(String(20), nullable=True)  # LB, CB, CDM, etc.
    shirt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Rendimiento
    minutes_played: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    was_substituted: Mapped[bool] = mapped_column(Boolean, default=False)
    substituted_in_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    substituted_out_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("fixture_id", "player_id", name="uq_fixture_player"),
        Index("ix_lineup_team_fixture", "team_id", "fixture_id"),
    )


# =============================================================
# 14. MATCH WEATHER (NUEVO)
# =============================================================

class MatchWeather(Base):
    """Condiciones climáticas durante el partido."""
    __tablename__ = "match_weather"

    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), primary_key=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    feels_like_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    conditions: Mapped[str | None] = mapped_column(String(40), nullable=True)  # Clear, Rain, Cloudy, Snow
    cloud_cover_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(40), nullable=True)  # open-meteo, manual
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


# =============================================================
# 15. MATCH CONTEXT (NUEVO — psicología + contexto especial)
# =============================================================

class MatchContext(Base):
    """Contexto especial del partido (derby, presión, descanso)."""
    __tablename__ = "match_context"

    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), primary_key=True)
    # Reposo
    home_rest_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_rest_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_consecutive_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_consecutive_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Tipo de partido
    is_derby: Mapped[bool] = mapped_column(Boolean, default=False)
    is_classic: Mapped[bool] = mapped_column(Boolean, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    is_playoff: Mapped[bool] = mapped_column(Boolean, default=False)
    # Presión psicológica (manual o calculada)
    psychological_pressure_home: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
    psychological_pressure_away: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
    # Notas libres del analista
    notes_manual: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_manual: Mapped[str | None] = mapped_column(String(500), nullable=True)  # comma-separated
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


# =============================================================
# 16. TRAVEL LOG (NUEVO — fatiga por viaje)
# =============================================================

class TravelLog(Base):
    """Registro de viaje previo a un partido (fatiga)."""
    __tablename__ = "travel_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), nullable=False, index=True)
    # Distancia y transporte
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    transport_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)  # plane, bus, train
    # Tiempos
    departure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    arrival_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    travel_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Venue anterior (de donde viene)
    from_venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# =============================================================
# 16b. REFEREES (NUEVO — árbitros de Liga MX)
# =============================================================
class Referee(Base):
    """Árbitro / referee (Liga MX)."""
    __tablename__ = "referees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks id
    full_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    common_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================
# 16c. REFEREE ASSIGNMENTS (NUEVO — qué árbitro pitó cada partido)
# =============================================================
class RefereeAssignment(Base):
    """Asignación de un árbitro a un partido (uno por partido)."""
    __tablename__ = "referee_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # sportmonks assignment id
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), nullable=False, index=True)
    referee_id: Mapped[int] = mapped_column(ForeignKey("referees.id"), nullable=False, index=True)
    type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 6=referee, 7=AR1, 8=AR2, 9=4th
    role: Mapped[str | None] = mapped_column(String(40), nullable=True)  # 'main', 'assistant_1', 'assistant_2', 'fourth'
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("fixture_id", "referee_id", "role", name="uq_fixture_referee_role"),
        Index("ix_referee_assignment_fixture", "fixture_id"),
        Index("ix_referee_assignment_referee", "referee_id"),
    )


# =============================================================
# 17. TEAM FORM (CALCULADO — últimos 5 partidos)
# =============================================================

class TeamForm(Base):
    """Forma reciente del equipo (snapshot calculado)."""
    __tablename__ = "team_form"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False, index=True)
    as_of_fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"), nullable=True)
    as_of_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Últimos 5 partidos
    last_n: Mapped[int] = mapped_column(Integer, default=5)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    goals_for: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)  # 3W+1D+0L
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # calculado -1 a +1

    __table_args__ = (
        Index("ix_teamform_team_date", "team_id", "as_of_date"),
    )


# =============================================================
# 18. PLAYER FORM (CALCULADO — últimos N partidos del jugador)
# =============================================================

class PlayerForm(Base):
    """Forma reciente del jugador."""
    __tablename__ = "player_form"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False, index=True)
    as_of_fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"), nullable=True)
    as_of_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_n: Mapped[int] = mapped_column(Integer, default=5)
    # Stats
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    # Derivados
    fatigue_index: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10, más alto = más cansado
    form_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # -1 a +1

    __table_args__ = (
        Index("ix_playerform_player_date", "player_id", "as_of_date"),
    )


# =============================================================
# 19. COACH FORM (CALCULADO — últimos N partidos del DT)
# =============================================================

class CoachForm(Base):
    """Forma reciente del DT (racha + presión)."""
    __tablename__ = "coach_form"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False, index=True)
    as_of_fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"), nullable=True)
    as_of_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_n: Mapped[int] = mapped_column(Integer, default=5)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    goals_for: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    # Presión
    pressure_index: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
    job_at_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    winless_streak: Mapped[int] = mapped_column(Integer, default=0)  # partidos sin ganar

    __table_args__ = (
        Index("ix_coachform_coach_date", "coach_id", "as_of_date"),
    )


# =============================================================
# Engine / Session
# =============================================================

def get_engine(url: str | None = None):
    """Crea el engine de SQLAlchemy."""
    db_url = url or DATABASE_URL
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, connect_args=connect_args, future=True)
    return engine


def init_db(url: str | None = None) -> None:
    """Crea todas las tablas en la BD."""
    engine = get_engine(url)
    if url and url.startswith("sqlite:///"):
        db_path = Path(url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    elif DATABASE_URL.startswith("sqlite:///"):
        PATHS.data_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    print(f"✅ BD inicializada en {DATABASE_URL}")


def get_session(url: str | None = None):
    """Devuelve una SessionFactory."""
    engine = get_engine(url)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def table_count(url: str | None = None) -> dict[str, int]:
    """Devuelve el conteo de registros por tabla."""
    engine = get_engine(url)
    counts = {}
    with engine.connect() as conn:
        for table_name in Base.metadata.tables:
            try:
                cnt = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table_name}").scalar()
                counts[table_name] = cnt or 0
            except Exception:
                counts[table_name] = 0
    return counts


# =============================================================
# Constantes: derbies y clásicos de Liga MX
# =============================================================

# Pares de equipos (team_id_sportmonks) que son derbies/clásicos
DERBIES_LIGA_MX: list[tuple[int, int]] = [
    # Clásico Nacional (América vs Chivas)
    (1, 2),  # IDs reales se llenan al ingestar
    # Clásico Regiomontano (Monterrey vs Tigres)
    (16, 11),
    # Clásico Capitalino (América vs Pumas)
    (1, 8),
    # Clásico Tapatío (Chivas vs Atlas)
    (2, 12),
    # Clásico Joven (América vs Cruz Azul)
    (1, 4),
]

CLASSICS_LIGA_MX: list[tuple[int, int]] = DERBIES_LIGA_MX  # por ahora iguales