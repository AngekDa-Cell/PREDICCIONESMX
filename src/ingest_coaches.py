"""
ingest_coaches.py — Ingiesta coaches y coach_tenures desde SportMonks.

Estrategia: el endpoint /coaches trae cada coach con .teams[] donde cada
team tiene {team_id, start, end, active, temporary}. Mapeamos esos datos
a la tabla coach_tenures cruzando fechas con nuestras seasons.

Uso:
    python3 -m proyectos.src.ingest_coaches
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SportMonksConfig
from .db import (
    Coach,
    CoachTenure,
    Season,
    get_session,
)
from .logging_setup import setup_logging
from .sportmonks_client import SportMonksClient


def parse_date(s: str | None):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:10] if "T" in s else s, "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def upsert_coach(session: Session, c: dict) -> Coach | None:
    cid = c.get("id")
    if not cid:
        return None
    coach = session.get(Coach, cid)
    dob = parse_date(c.get("date_of_birth"))
    name = c.get("name") or c.get("display_name") or c.get("common_name") or f"Coach {cid}"
    nat = c.get("nationality")
    if isinstance(nat, dict):
        nat = nat.get("name")
    if coach is None:
        coach = Coach(
            id=cid, full_name=name,
            first_name=c.get("firstname"), last_name=c.get("lastname"),
            common_name=c.get("common_name") or c.get("display_name"),
            date_of_birth=dob, nationality=nat,
            photo_url=c.get("image_path"),
            tactical_style=None, formation_preference=None,
            years_experience=None, meta_json=c,
        )
        session.add(coach)
    else:
        coach.full_name = name
        coach.first_name = c.get("firstname") or coach.first_name
        coach.last_name = c.get("lastname") or coach.last_name
        coach.common_name = c.get("common_name") or coach.common_name
        coach.date_of_birth = dob or coach.date_of_birth
        coach.nationality = nat or coach.nationality
        coach.photo_url = c.get("image_path") or coach.photo_url
        coach.meta_json = c
    return coach


def get_seasons_in_range(session: Session, start_date, end_date) -> list[Season]:
    """Devuelve las seasons de la BD que caen dentro del rango [start, end]."""
    if not start_date:
        return []
    end = end_date or datetime.utcnow().date()
    seasons = session.execute(select(Season)).scalars().all()
    matches = []
    for s in seasons:
        if not s.start_date or not s.end_date:
            continue
        s_start = s.start_date.date() if hasattr(s.start_date, 'date') else s.start_date
        s_end = s.end_date.date() if hasattr(s.end_date, 'date') else s.end_date
        # La season solapa con el rango del tenure si:
        # s.start <= end AND s.end >= start
        if s_start <= end and s_end >= start_date:
            matches.append(s)
    return matches


def upsert_tenure(session: Session, coach_id: int, team_id: int, season_id: int,
                  start_date, end_date, is_current: bool, meta: dict) -> CoachTenure:
    existing = session.query(CoachTenure).filter_by(
        coach_id=coach_id, team_id=team_id, season_id=season_id
    ).first()
    if existing:
        existing.start_date = start_date or existing.start_date
        existing.end_date = end_date or existing.end_date
        existing.is_current = is_current
        existing.meta_json = meta
        return existing
    tenure = CoachTenure(
        coach_id=coach_id, team_id=team_id, season_id=season_id,
        start_date=start_date, end_date=end_date,
        is_current=is_current, meta_json=meta,
    )
    session.add(tenure)
    return tenure


def main() -> int:
    setup_logging("INFO")

    cfg = SportMonksConfig.from_env()
    Session = get_session()

    coach_count = 0
    tenure_count = 0
    skipped = 0

    with SportMonksClient(cfg) as client, Session() as session:
        print("🔄 Descargando todos los coaches (con sus equipos)...")
        all_coaches = client.get_all("coaches", {"include": "teams", "per_page": 50})
        print(f"  📦 {len(all_coaches)} coaches totales")

        for c in all_coaches:
            cid = c.get("id")
            if not cid:
                continue
            coach = upsert_coach(session, c)
            if coach:
                coach_count += 1

            teams = c.get("teams") or []
            for t in teams:
                team_id = t.get("team_id")
                if not team_id:
                    continue
                start = parse_date(t.get("start"))
                end = parse_date(t.get("end"))
                is_current = bool(t.get("active")) and not end

                # Mapear a seasons que correspondan al rango de fechas
                if not start:
                    skipped += 1
                    continue
                matching_seasons = get_seasons_in_range(session, start, end)
                if not matching_seasons:
                    skipped += 1
                    continue
                for s in matching_seasons:
                    upsert_tenure(
                        session, cid, team_id, s.id,
                        start_date=start, end_date=end,
                        is_current=is_current, meta=t,
                    )
                    tenure_count += 1

            if coach_count % 50 == 0:
                session.commit()
                print(f"  ... {coach_count} coaches procesados, {tenure_count} tenures")
        session.commit()

    print(f"\n{'='*50}")
    print(f"📊 Resumen final:")
    print(f"  • Coaches en BD:        {coach_count:,}")
    print(f"  • Tenures registrados:  {tenure_count:,}")
    print(f"  • Tenures sin season:   {skipped:,}")
    print(f"{'='*50}")
    return 0


if __name__ == "__main__":
    sys.exit(main())