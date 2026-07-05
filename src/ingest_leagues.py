"""
ingest_leagues.py — Ingiesta las ligas configuradas a la BD.

Uso:
    python3 src/ingest_leagues.py
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from .config import SportMonksConfig
from .db import League, get_session, init_db
from .logging_setup import setup_logging
from .sportmonks_client import SportMonksClient


LEAGUES_TO_INGEST = [
    ("liga_mx", "Liga MX"),
    ("liga_expansion", "Liga de Expansión MX"),
]


def upsert_league(session, sm_id: int, name: str, country: str = "Mexico") -> League:
    """Inserta o actualiza una liga por su sportmonks_id."""
    lg = session.get(League, sm_id)
    if lg is None:
        lg = League(id=sm_id, name=name, country=country, is_active=True)
        session.add(lg)
        print(f"  + Nueva liga: id={sm_id} name={name}")
    else:
        lg.name = name
        lg.country = country
        lg.is_active = True
        print(f"  ~ Liga actualizada: id={sm_id} name={name}")
    session.flush()
    return lg


def main() -> int:
    setup_logging("INFO")
    init_db()

    cfg = SportMonksConfig.from_env()
    Session = get_session()

    league_ids = {
        "liga_mx": cfg.league_liga_mx,
        "liga_expansion": cfg.league_liga_expansion,
    }

    with SportMonksClient(cfg) as client, Session() as session:
        for slug, display_name in LEAGUES_TO_INGEST:
            sm_id = league_ids[slug]
            print(f"→ Ingestando {display_name} (id={sm_id})")
            try:
                resp = client.get_league(sm_id)
                data = resp.get("data", {})
                api_name = data.get("name", display_name)
                country = data.get("country")
                if isinstance(country, dict):
                    country = country.get("name", "Mexico")
                country = country or "Mexico"
                upsert_league(session, sm_id, api_name, country)
            except Exception as e:
                print(f"  ⚠️  Error con {slug}: {e}")
                session.rollback()
                continue

        session.commit()

    print("\n✅ Ingesta de ligas completada.")
    # Mostrar resumen
    with Session() as session:
        all_leagues = session.execute(select(League)).scalars().all()
        for lg in all_leagues:
            print(f"   • {lg.id:>4} | {lg.name:<35} | {lg.country}")
    return 0


if __name__ == "__main__":
    sys.exit(main())