"""
ingest_referees.py — Ingiere árbitros y sus asignaciones a partidos de Liga MX.

SportMonks v3 expone los árbitros por temporada vía:
    GET /referees/seasons/{season_id}?include=fixtures
donde cada referee trae los fixtures que pitó (más asistentes). Solo nos
interesan los main referees (type_id=6).

Uso:
    python3 -m proyectos.src.ingest_referees
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

from sqlalchemy.orm import Session

from .config import SportMonksConfig
from .db import (
    Referee,
    RefereeAssignment,
    Season,
    get_session,
)
from .logging_setup import setup_logging
from .sportmonks_client import SportMonksClient


# type_id=6 es el main referee (verificado en API)
MAIN_REFEREE_TYPE_ID: int = 6

# Mapeo de type_id → role para guardar histórico (no usamos asistentes para
# predecir, pero los guardamos para futuro análisis)
TYPE_ID_TO_ROLE: dict[int, str] = {
    6: "main",
    7: "assistant_1",
    8: "assistant_2",
    9: "fourth",
}


def upsert_referee(session: Session, r: dict[str, Any]) -> Referee | None:
    """Inserta/actualiza un árbitro."""
    rid = r.get("id")
    if not rid:
        return None
    ref = session.get(Referee, rid)
    name = (
        r.get("name")
        or r.get("display_name")
        or r.get("common_name")
        or f"Referee {rid}"
    )
    common = r.get("common_name") or r.get("display_name") or name
    if ref is None:
        ref = Referee(
            id=rid,
            full_name=name,
            first_name=r.get("firstname"),
            last_name=r.get("lastname"),
            common_name=common,
            display_name=r.get("display_name"),
            image_path=r.get("image_path"),
            country_id=r.get("country_id"),
            meta_json=r,
        )
        session.add(ref)
    else:
        ref.full_name = name
        ref.first_name = r.get("firstname") or ref.first_name
        ref.last_name = r.get("lastname") or ref.last_name
        ref.common_name = common
        ref.display_name = r.get("display_name") or ref.display_name
        ref.image_path = r.get("image_path") or ref.image_path
        ref.country_id = r.get("country_id") or ref.country_id
        ref.meta_json = r
    return ref


def upsert_assignment(session: Session, a: dict[str, Any]) -> RefereeAssignment | None:
    """Inserta/actualiza una asignación árbitro-fixture."""
    aid = a.get("id")
    fid = a.get("fixture_id")
    rid = a.get("referee_id")
    if not (aid and fid and rid):
        return None
    existing = session.get(RefereeAssignment, aid)
    role = TYPE_ID_TO_ROLE.get(a.get("type_id"))
    if existing is None:
        existing = RefereeAssignment(
            id=aid,
            fixture_id=fid,
            referee_id=rid,
            type_id=a.get("type_id"),
            role=role,
            meta_json=a,
        )
        session.add(existing)
    else:
        existing.type_id = a.get("type_id") or existing.type_id
        existing.role = role or existing.role
        existing.meta_json = a
    return existing


def ingest_season_referees(
    client: SportMonksClient,
    session: Session,
    season: Season,
) -> dict[str, int]:
    """Ingiere árbitros y asignaciones de una temporada."""
    log = logging.getLogger(__name__)
    log.info(f"Ingestando referees temporada {season.id} ({season.name})")
    t0 = time.time()

    # SportMonks requiere cursor cuando hay paginación, así que usamos get_all
    payload = client._request(
        f"referees/seasons/{season.id}",
        {"include": "fixtures", "per_page": 100},
    )
    # Por si trae una página, iteramos manualmente
    all_refs = payload.get("data", []) or []
    pagination = payload.get("pagination", {}) or {}
    cursor_raw = pagination.get("next_cursor")

    pages = 1
    while cursor_raw:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(cursor_raw)
        cursor = parse_qs(parsed.query).get("cursor", [None])[0]
        if not cursor:
            break
        payload = client._request(
            f"referees/seasons/{season.id}",
            {"include": "fixtures", "cursor": cursor},
        )
        all_refs.extend(payload.get("data", []) or [])
        cursor_raw = (payload.get("pagination", {}) or {}).get("next_cursor")
        pages += 1

    refs_added = 0
    asg_added = 0
    main_added = 0

    for ref_data in all_refs:
        upsert_referee(session, ref_data)
        refs_added += 1
        for fix_data in ref_data.get("fixtures", []) or []:
            upsert_assignment(session, fix_data)
            asg_added += 1
            if fix_data.get("type_id") == MAIN_REFEREE_TYPE_ID:
                main_added += 1

    elapsed = time.time() - t0
    log.info(
        f"  → referees={refs_added} | assignments={asg_added} (main={main_added}) | "
        f"pages={pages} | {elapsed:.1f}s"
    )
    return {
        "refs": refs_added,
        "assignments": asg_added,
        "main": main_added,
        "pages": pages,
    }


def main() -> None:
    setup_logging("INFO")
    log = logging.getLogger(__name__)
    cfg = SportMonksConfig.from_env()
    client = SportMonksClient(cfg)
    SessionFactory = get_session()
    session = SessionFactory()

    log.info("=" * 60)
    log.info("INGESTA DE REFEREES — Liga MX + Liga Expansión")
    log.info("=" * 60)

    try:
        # 1) Iterar todas las temporadas de Liga MX (743) y Liga Expansión (749)
        from sqlalchemy import select
        stmt = (
            select(Season)
            .where(Season.league_id.in_([743, 749]))
            .order_by(Season.id)
        )
        seasons = session.execute(stmt).scalars().all()
        log.info(f"Temporadas a ingestar: {len(seasons)}")

        grand_totals = {"refs": 0, "assignments": 0, "main": 0, "pages": 0}
        for s in seasons:
            try:
                totals = ingest_season_referees(client, session, s)
                session.commit()
                for k, v in totals.items():
                    grand_totals[k] += v
            except Exception as e:
                log.error(f"  ✗ Error temporada {s.id}: {e}")
                session.rollback()

        log.info("=" * 60)
        log.info(
            f"TOTAL → referees nuevos={grand_totals['refs']} | "
            f"assignments nuevos={grand_totals['assignments']} | "
            f"main={grand_totals['main']} | api_pages={grand_totals['pages']}"
        )
        log.info("=" * 60)

    finally:
        client.close()
        session.close()


if __name__ == "__main__":
    main()