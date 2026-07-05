"""
ingest_seasons_targeted.py — Ingiesta equipos y fixtures de las temporadas seleccionadas.

Por defecto: últimas 5 temporadas finalizadas de Liga MX y Liga Expansión.
Para un MVP de modelo predictivo, 5 temporadas (~340 partidos Liga MX)
son suficientes.

Uso:
    python3 -m proyectos.src.ingest_seasons_targeted
    # o:
    python3 -m proyectos.src.ingest_seasons_targeted --seasons 2024/2025 2025/2026
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SportMonksConfig
from .db import (
    Fixture,
    FixtureEvent,
    FixtureStatistic,
    League,
    Season,
    Team,
    Venue,
    get_session,
    init_db,
)
from .logging_setup import setup_logging
from .sportmonks_client import SportMonksClient, SportMonksError


# =============================================================
# Helpers de parseo
# =============================================================

def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# =============================================================
# Upserts
# =============================================================

def upsert_venue(session: Session, v: dict) -> Venue | None:
    if not v or not v.get("id"):
        return None
    venue = session.get(Venue, v["id"])
    if venue is None:
        venue = Venue(
            id=v["id"],
            name=v.get("name") or f"Venue {v['id']}",
            city=(v.get("city") or None),
            capacity=v.get("capacity"),
        )
        session.add(venue)
    else:
        if v.get("name"):
            venue.name = v["name"]
        venue.city = v.get("city") or venue.city
        venue.capacity = v.get("capacity") or venue.capacity
    return venue


def upsert_team(session: Session, t: dict) -> Team | None:
    if not t or not t.get("id"):
        return None
    tid = t["id"]
    team = session.get(Team, tid)
    venue_id = None
    if t.get("venue_id"):
        venue_id = t["venue_id"]
    logo = t.get("image_path")

    if team is None:
        team = Team(
            id=tid,
            name=t.get("name") or f"Team {tid}",
            short_code=t.get("short_code"),
            country=(t.get("country") or {}).get("name") if isinstance(t.get("country"), dict) else t.get("country"),
            founded=t.get("founded"),
            venue_id=venue_id,
            logo_url=logo,
        )
        session.add(team)
    else:
        if t.get("name"):
            team.name = t["name"]
        team.short_code = t.get("short_code") or team.short_code
        if t.get("country"):
            country = (t.get("country") or {}).get("name") if isinstance(t.get("country"), dict) else t.get("country")
            team.country = country or team.country
        team.venue_id = venue_id or team.venue_id
        team.logo_url = logo or team.logo_url
    return team


def upsert_fixture(session: Session, f: dict, season_id: int, league_id: int) -> Fixture | None:
    """Inserta o actualiza un fixture."""
    fid = f.get("id")
    if not fid:
        return None

    # participants viene cuando pedimos include=participants
    participants = f.get("participants") or []
    home_id = away_id = None
    for p in participants:
        meta = p.get("meta") or {}
        loc = (meta.get("location") or "").lower()
        pid = p.get("id")
        if not pid:
            continue
        if loc == "home":
            home_id = pid
        elif loc == "away":
            away_id = pid
    # Fallback: si no hay participants con meta.location, intentar otros campos
    if not home_id or not away_id:
        # Algunos endpoints ponen 'localteam_id' y 'visitorteam_id' en scores
        scores = f.get("scores") or []
        for s in scores:
            desc = (s.get("description") or "").lower()
            sid = s.get("participant_id") or s.get("scored_by") or s.get("team_id")
            if not sid:
                continue
            if desc == "current" or desc == "full":
                if not home_id:
                    home_id = sid
                elif not away_id:
                    away_id = sid

    if not home_id or not away_id:
        # No podemos crear el fixture sin los dos equipos
        return None

    starting = parse_dt(f.get("starting_at"))
    if not starting:
        return None
    starting = to_utc(starting).replace(tzinfo=None) if to_utc(starting) else None
    if not starting:
        return None

    state = None
    ss = f.get("state") or {}
    if isinstance(ss, dict):
        state = ss.get("short_code") or ss.get("state") or ss.get("name")
    elif isinstance(ss, str):
        state = ss

    # Scores (obtenidos de include=fixtures.scores)
    # Estructura SportMonks: cada score tiene:
    #   {id, participant_id, score: {goals, participant}, description, location, type}
    #   description: "CURRENT" | "FULL" | "1STHALF" | "2NDHALF" | "EXTRATIME" | "PENALTY"
    #   participant: "home" | "away"
    #   location: "home" | "away"
    # goals: entero (o None si no hubo)
    home_score = away_score = None
    home_ht = away_ht = None

    def _extract_score_value(sc: dict) -> int | None:
        s = sc.get("score")
        if isinstance(s, dict):
            return s.get("goals")
        if isinstance(s, int):
            return s
        return None

    def _is_home(sc: dict) -> bool:
        # SportMonks pone 'home'/'away' en score.participant o en location
        s = sc.get("score")
        if isinstance(s, dict):
            if (s.get("participant") or "").lower() == "home":
                return True
            if (s.get("participant") or "").lower() == "away":
                return False
        loc = (sc.get("location") or "").lower()
        if loc == "home":
            return True
        if loc == "away":
            return False
        # Fallback: participant_id
        pid = sc.get("participant_id")
        if pid == home_id:
            return True
        if pid == away_id:
            return False
        return False

    for sc in f.get("scores") or []:
        desc = (sc.get("description") or "").upper()
        goals = _extract_score_value(sc)
        if goals is None:
            continue
        is_home = _is_home(sc)

        if desc in ("CURRENT", "FULL", "ALL"):
            # Resultado final del partido
            if is_home:
                if home_score is None:
                    home_score = goals
            else:
                if away_score is None:
                    away_score = goals
        elif desc in ("1STHALF", "FIRSTHALF", "HALFTIME", "1H"):
            if is_home:
                home_ht = goals
            else:
                away_ht = goals
        elif desc in ("2NDHALF", "SECONDHALF", "2H"):
            # A veces '2ndhalf' es el resultado parcial del 2T
            # Si solo hay 2ndhalf pero no full, puede ser el marcador total
            if is_home:
                if home_ht is None:
                    home_ht = goals
            else:
                if away_ht is None:
                    away_ht = goals

    round_name = None
    rnd = f.get("round") or {}
    if isinstance(rnd, dict):
        round_name = rnd.get("name") or rnd.get("stage")

    fixture = session.get(Fixture, fid)
    if fixture is None:
        fixture = Fixture(
            id=fid,
            season_id=season_id,
            league_id=league_id,
            home_team_id=home_id,
            away_team_id=away_id,
            starting_at=starting,
            state=state,
            round=round_name,
            home_score=home_score,
            away_score=away_score,
            home_ht_score=home_ht,
            away_ht_score=away_ht,
            meta_json=f,
        )
        session.add(fixture)
    else:
        fixture.home_team_id = home_id
        fixture.away_team_id = away_id
        fixture.starting_at = starting
        fixture.state = state or fixture.state
        fixture.round = round_name or fixture.round
        fixture.home_score = home_score
        fixture.away_score = away_score
        fixture.home_ht_score = home_ht
        fixture.away_ht_score = away_ht
        fixture.meta_json = f
    return fixture


def upsert_events(session: Session, fixture: Fixture, events: list[dict]) -> int:
    """Inserta/actualiza eventos de un fixture."""
    n = 0
    for e in events:
        eid = e.get("id")
        if not eid:
            continue
        # Verificar si ya existe
        existing = session.get(FixtureEvent, eid)
        team_id = e.get("participant_id") or (e.get("team_id") if isinstance(e.get("team"), int) else None)
        if team_id is None and isinstance(e.get("participant"), dict):
            team_id = e["participant"].get("id")
        player_id = None
        if isinstance(e.get("player"), dict):
            player_id = e["player"].get("id")
        elif isinstance(e.get("player_id"), int):
            player_id = e["player_id"]

        minute = e.get("minute")
        extra = e.get("extra_minute")
        type_ = e.get("type") or e.get("type_name")
        detail = e.get("detail")

        if existing:
            existing.team_id = team_id or existing.team_id
            existing.player_id = player_id or existing.player_id
            existing.minute = minute if minute is not None else existing.minute
            existing.extra_minute = extra if extra is not None else existing.extra_minute
            existing.type = type_ or existing.type
            existing.detail = detail or existing.detail
        else:
            session.add(FixtureEvent(
                id=eid,
                fixture_id=fixture.id,
                team_id=team_id,
                player_id=player_id,
                minute=minute,
                extra_minute=extra,
                type=type_,
                detail=detail,
                meta_json=e,
            ))
            n += 1
    return n


def upsert_statistics(session: Session, fixture: Fixture, stats: list[dict]) -> int:
    """Inserta/actualiza estadísticas por equipo de un fixture."""
    n = 0
    for s in stats:
        # En SportMonks, statistics viene como array de objetos con:
        # {type: {code, name, developer_name}, data: {value}, participant_id, location, ...}
        stat_type = None
        if isinstance(s.get("type"), dict):
            stat_type = s["type"].get("code") or s["type"].get("name")
        elif isinstance(s.get("type"), str):
            stat_type = s["type"]
        if not stat_type:
            continue
        team_id = s.get("participant_id") or s.get("team_id")
        value = s.get("data", {}).get("value") if isinstance(s.get("data"), dict) else s.get("value")
        if value is None or team_id is None:
            continue
        # Buscar existente por (fixture, team, type)
        existing = session.query(FixtureStatistic).filter_by(
            fixture_id=fixture.id, team_id=team_id, stat_type=stat_type
        ).first()
        if existing:
            existing.stat_value = float(value)
            existing.meta_json = s
        else:
            session.add(FixtureStatistic(
                fixture_id=fixture.id,
                team_id=team_id,
                stat_type=stat_type,
                stat_value=float(value),
                meta_json=s,
            ))
            n += 1
    return n


# =============================================================
# Ingesta principal
# =============================================================

# Include string optimizado para predicción:
# - participants: home/away
# - scores: resultado final y al descanso
# - events: goles, tarjetas, sustituciones
# - statistics: posesión, tiros, córners, etc. (con .type para nombre/código)
# Omitidos por peso/uso: lineups, venue, round, league, season
# El cliente antepondrá 'fixtures.' a cada parte para anidar el include
# en la llamada a /seasons/{id}?include=fixtures.participants;...
FULL_INCLUDE = "participants;scores;events;statistics.type"


def ingest_season(
    client: SportMonksClient,
    session: Session,
    season: Season,
    include_teams: bool = True,
) -> dict:
    """Ingiesta equipos + fixtures + eventos + stats de una temporada."""
    log = {
        "season_id": season.id,
        "season_name": season.name,
        "league_id": season.league_id,
        "teams_added": 0,
        "fixtures_total": 0,
        "fixtures_with_events": 0,
        "events_added": 0,
        "stats_added": 0,
    }

    print(f"\n→ {season.league.name if season.league else season.league_id} | {season.name} (id={season.id})")

    # 1. Equipos
    if include_teams:
        teams = client.get_season_teams(season.id)
        for t in teams:
            upsert_team(session, t)
        session.flush()
        log["teams_added"] = len(teams)
        print(f"  ✓ {len(teams)} equipos")

    # 2. Fixtures con todos los includes
    print(f"  ⏳ Bajando fixtures con includes completos...")
    fixtures = client.get_fixtures_by_season(season.id, include=FULL_INCLUDE)
    log["fixtures_total"] = len(fixtures)

    events_added = 0
    stats_added = 0
    fixtures_with_events = 0
    for f in fixtures:
        fx = upsert_fixture(session, f, season.id, season.league_id)
        if fx is None:
            continue
        # Eventos
        events = f.get("events") or []
        if events:
            n = upsert_events(session, fx, events)
            events_added += n
            fixtures_with_events += 1
        # Stats
        stats = f.get("statistics") or []
        if stats:
            n = upsert_statistics(session, fx, stats)
            stats_added += n

    log["events_added"] = events_added
    log["stats_added"] = stats_added
    log["fixtures_with_events"] = fixtures_with_events

    print(f"  ✓ {log['fixtures_total']} fixtures | {events_added} eventos | {stats_added} stats")
    return log


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seasons",
        nargs="+",
        help="Nombres de temporadas exactas (ej. '2024/2025'). Por defecto: las últimas 5 finalizadas.",
    )
    parser.add_argument(
        "--league",
        type=int,
        help="Filtrar por id de liga (743=Liga MX, 749=Expansión). Por defecto: ambas.",
    )
    args = parser.parse_args()

    setup_logging("INFO")
    init_db()

    cfg = SportMonksConfig.from_env()
    Session = get_session()

    with Session() as session:
        q = select(Season).order_by(Season.league_id, Season.start_date.desc())
        if args.league:
            q = q.where(Season.league_id == args.league)
        all_seasons = session.execute(q).scalars().all()

        if args.seasons:
            target = [s for s in all_seasons if s.name in args.seasons]
        else:
            # Últimas 5 temporadas finalizadas POR CADA LIGA
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            finished = [s for s in all_seasons if s.end_date and s.end_date < now]
            # Agrupar por liga y tomar 5 más recientes de cada una
            target = []
            by_league: dict[int, list[Season]] = {}
            for s in finished:
                by_league.setdefault(s.league_id, []).append(s)
            for lid in sorted(by_league):
                # Ya están ordenadas por start_date desc
                target.extend(by_league[lid][:5])

        if not target:
            print("❌ No hay temporadas objetivo.")
            return 1

        print(f"🎯 Temporadas objetivo ({len(target)}):")
        for s in target:
            print(f"   • L{s.league_id} | {s.id} | {s.name} ({s.start_date.date() if s.start_date else '?'} → {s.end_date.date() if s.end_date else '?'})")
        print()

    all_logs = []
    with SportMonksClient(cfg) as client, Session() as session:
        for s in target:
            # refrescar objeto
            season = session.get(Season, s.id)
            if not season:
                continue
            try:
                log = ingest_season(client, session, season, include_teams=True)
                session.commit()
                all_logs.append(log)
            except SportMonksError as e:
                print(f"  ⚠️  Error: {e}")
                session.rollback()
                continue
            except Exception as e:
                print(f"  💥 Error inesperado: {type(e).__name__}: {e}")
                session.rollback()
                continue

    # Resumen final
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE INGESTA")
    print("=" * 60)
    total_fx = sum(l["fixtures_total"] for l in all_logs)
    total_ev = sum(l["events_added"] for l in all_logs)
    total_st = sum(l["stats_added"] for l in all_logs)
    print(f"Temporadas procesadas: {len(all_logs)}")
    print(f"Total fixtures:        {total_fx}")
    print(f"Total eventos:         {total_ev}")
    print(f"Total stats:           {total_st}")
    print()
    for l in all_logs:
        print(f"  • L{l['league_id']} {l['season_name']:>10}: "
              f"{l['fixtures_total']:>4} fx | {l['events_added']:>5} ev | {l['stats_added']:>5} st")

    return 0


if __name__ == "__main__":
    sys.exit(main())