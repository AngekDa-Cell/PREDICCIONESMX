"""
ingest_seasons.py — Ingiesta las temporadas (seasons) de cada liga.

Uso:
    python3 src/ingest_seasons.py
"""

from __future__ import annotations

import sys
from datetime import datetime

from sqlalchemy import select

from .config import SportMonksConfig
from .db import League, Season, get_session, init_db
from .logging_setup import setup_logging
from .sportmonks_client import SportMonksClient


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    setup_logging("INFO")
    init_db()

    cfg = SportMonksConfig.from_env()
    Session = get_session()
    league_ids = [cfg.league_liga_mx, cfg.league_liga_expansion]

    with SportMonksClient(cfg) as client, Session() as session:
        for league_id in league_ids:
            league = session.get(League, league_id)
            if not league:
                print(f"⚠️  Liga {league_id} no está en BD. Corre primero ingest_leagues.py")
                continue

            print(f"→ Temporadas de {league.name} (id={league_id})")
            seasons = client.get_league_seasons(league_id)
            now = datetime.utcnow()
            current_marked = False
            for s in seasons:
                sid = s["id"]
                name = s.get("name", "")
                start = parse_dt(s.get("starting_at"))
                end = parse_dt(s.get("ending_at"))
                is_current = bool(start and end and start <= now <= end)

                existing = session.get(Season, sid)
                if existing:
                    existing.name = name
                    existing.start_date = start
                    existing.end_date = end
                    existing.is_current = is_current
                    print(f"  ~ {sid:>6} | {name:<35} | {'CURRENT' if is_current else ''}")
                else:
                    session.add(Season(
                        id=sid,
                        league_id=league_id,
                        name=name,
                        start_date=start,
                        end_date=end,
                        is_current=is_current,
                    ))
                    print(f"  + {sid:>6} | {name:<35} | {'CURRENT' if is_current else ''}")
                if is_current:
                    current_marked = True

            session.commit()
            if not current_marked:
                print(f"  (ninguna temporada marcada como current — verifica fechas)")

    print("\n✅ Ingesta de temporadas completada.")
    with Session() as session:
        rows = session.execute(
            select(Season).order_by(Season.league_id, Season.start_date.desc())
        ).scalars().all()
        for r in rows[:20]:
            cur = " ⭐" if r.is_current else ""
            print(f"   • L{r.league_id} | {r.id:>6} | {r.name:<35}{cur}")
    return 0


if __name__ == "__main__":
    sys.exit(main())