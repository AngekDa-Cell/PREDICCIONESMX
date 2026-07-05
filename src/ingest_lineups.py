"""
ingest_lineups.py — Ingiesta alineaciones de los fixtures existentes.

Por cada fixture, obtiene su lineup con detalle:
- is_starter, is_captain, position, shirt_number
- minutes_played, rating, goals, assists
- yellow/red cards, was_substituted

Uso:
    python3 -m proyectos.src.ingest_lineups
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SportMonksConfig
from .db import (
    Fixture,
    FixtureLineup,
    Player,
    Season,
    get_session,
)
from .logging_setup import setup_logging
from .sportmonks_client import SportMonksClient


def upsert_lineup(session: Session, fixture_id: int, l: dict) -> FixtureLineup | None:
    """Inserta/actualiza una alineación."""
    player_id = l.get("player_id")
    if not player_id:
        return None
    team_id = l.get("team_id")
    if not team_id:
        return None

    # Posición
    pos = l.get("position") or {}
    pos_group = None
    pos_detail = None
    if isinstance(pos, dict):
        pos_group = pos.get("name") or pos.get("code")  # "Goalkeeper", "Defender", etc.
        pos_detail = pos.get("code") or pos.get("name")
    elif isinstance(pos, str):
        pos_group = pos

    # Rating puede venir como dict
    rating = l.get("rating")
    if isinstance(rating, dict):
        rating = rating.get("rating") or rating.get("value")

    existing = session.query(FixtureLineup).filter_by(
        fixture_id=fixture_id, player_id=player_id
    ).first()
    if existing:
        existing.team_id = team_id
        existing.is_starter = bool(l.get("type") in (None, "lineup"))  # 'lineup' = titular
        existing.is_captain = bool(l.get("captain") or l.get("is_captain"))
        existing.position_group = pos_group or existing.position_group
        existing.position_detail = pos_detail or existing.position_detail
        existing.shirt_number = l.get("jersey_number") or existing.shirt_number
        existing.minutes_played = l.get("minutes_played") or existing.minutes_played
        existing.rating = rating or existing.rating
        existing.goals = l.get("goals") or 0
        existing.assists = l.get("assists") or 0
        existing.yellow_cards = l.get("yellowcards") or 0
        existing.red_cards = l.get("redcards") or 0
        existing.was_substituted = bool(l.get("substituted"))
        existing.substituted_in_minute = l.get("substituted_in_minute")
        existing.substituted_out_minute = l.get("substituted_out_minute")
        existing.meta_json = l
        return existing
    new = FixtureLineup(
        fixture_id=fixture_id, player_id=player_id, team_id=team_id,
        is_starter=bool(l.get("type") in (None, "lineup")),
        is_captain=bool(l.get("captain") or l.get("is_captain")),
        position_group=pos_group, position_detail=pos_detail,
        shirt_number=l.get("jersey_number"),
        minutes_played=l.get("minutes_played"),
        rating=rating, goals=l.get("goals") or 0, assists=l.get("assists") or 0,
        yellow_cards=l.get("yellowcards") or 0, red_cards=l.get("redcards") or 0,
        was_substituted=bool(l.get("substituted")),
        substituted_in_minute=l.get("substituted_in_minute"),
        substituted_out_minute=l.get("substituted_out_minute"),
        meta_json=l,
    )
    session.add(new)
    return new


def upsert_player_from_lineup(session: Session, l: dict) -> Player | None:
    """Crea/actualiza un Player desde la info de la lineup."""
    pid = l.get("player_id")
    if not pid:
        return None
    player = session.get(Player, pid)
    name = l.get("player_name") or l.get("name") or f"Player {pid}"
    # La API puede traer player como sub-object
    p_data = l.get("player") or {}
    if isinstance(p_data, dict) and p_data:
        pid = p_data.get("id") or pid
        name = p_data.get("display_name") or p_data.get("name") or p_data.get("common_name") or name
        first = p_data.get("firstname")
        last = p_data.get("lastname")
        common = p_data.get("common_name")
        dob_s = p_data.get("date_of_birth")
        if dob_s:
            try:
                dob = datetime.strptime(dob_s[:10], "%Y-%m-%d").date()
            except Exception:
                dob = None
        else:
            dob = None
        nat = p_data.get("nationality")
        if isinstance(nat, dict):
            nat = nat.get("name")
        pos_data = p_data.get("position") or {}
        primary_pos = pos_data.get("name") if isinstance(pos_data, dict) else pos_data
        pos_detail = pos_data.get("code") if isinstance(pos_data, dict) else None
        height = p_data.get("height")
        weight = p_data.get("weight")
        foot = p_data.get("preferred_foot")
        photo = p_data.get("image_path")
    else:
        first = last = common = None
        dob = None
        nat = None
        primary_pos = pos_detail = None
        height = weight = foot = photo = None

    if player is None:
        player = Player(
            id=pid, full_name=name, first_name=first, last_name=last,
            common_name=common, date_of_birth=dob, nationality=nat,
            primary_position=primary_pos, position_detail=pos_detail,
            height_cm=height, weight_kg=weight, preferred_foot=foot,
            photo_url=photo, meta_json=l,
        )
        session.add(player)
    else:
        if not player.full_name or player.full_name.startswith("Player "):
            player.full_name = name
        player.first_name = first or player.first_name
        player.last_name = last or player.last_name
        player.common_name = common or player.common_name
        player.date_of_birth = dob or player.date_of_birth
        player.nationality = nat or player.nationality
        player.primary_position = primary_pos or player.primary_position
        player.position_detail = pos_detail or player.position_detail
        player.height_cm = height or player.height_cm
        player.weight_kg = weight or player.weight_kg
        player.preferred_foot = foot or player.preferred_foot
        player.photo_url = photo or player.photo_url
    return player


def main() -> int:
    setup_logging("INFO")

    cfg = SportMonksConfig.from_env()
    Session = get_session()

    # Obtener temporadas objetivo (5 últimas finalizadas por liga)
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
        target = []
        for lid in sorted(by_league):
            target.extend(by_league[lid][:5])
        print(f"🎯 {len(target)} temporadas objetivo")

    lineup_count = 0
    player_count = 0
    fixture_count = 0

    with SportMonksClient(cfg) as client, Session() as session:
        for s in target:
            season = session.get(Season, s.id)
            if not season:
                continue
            print(f"\n→ Liga {s.league_id} | {s.name} (id={s.id})", flush=True)
            try:
                # Lineups por temporada con detalle del player
                r = client._request(f"seasons/{s.id}", {
                    "include": "fixtures.lineups.player"
                })
            except Exception as e:
                print(f"  ⚠️  Error: {e}", flush=True)
                continue
            fixtures = r.get("data", {}).get("fixtures", [])
            print(f"  📦 {len(fixtures)} fixtures", flush=True)
            season_players = 0
            season_lineups = 0
            for idx_f, f in enumerate(fixtures):
                fid = f.get("id")
                fixture = session.get(Fixture, fid)
                if not fixture:
                    continue
                lineups = f.get("lineups") or []
                if not lineups:
                    continue
                fixture_count += 1
                for l in lineups:
                    p = upsert_player_from_lineup(session, l)
                    if p:
                        season_players += 1
                    lineup = upsert_lineup(session, fid, l)
                    if lineup:
                        season_lineups += 1
                # Commit cada 50 fixtures para no acumular
                if (idx_f + 1) % 50 == 0:
                    session.commit()
                    print(f"    ... {idx_f+1}/{len(fixtures)} fixtures, {season_lineups} lineups", flush=True)
            session.commit()
            lineup_count += season_lineups
            player_count += season_players
            print(f"  ✓ {season_lineups} lineups, {season_players} players", flush=True)

    print(f"\n{'='*50}")
    print(f"📊 Resumen final:")
    print(f"  • Fixtures con lineup:  {fixture_count:,}")
    print(f"  • Total lineups:        {lineup_count:,}")
    print(f"  • Players registrados:  {player_count:,}")
    print(f"{'='*50}")
    return 0


if __name__ == "__main__":
    sys.exit(main())