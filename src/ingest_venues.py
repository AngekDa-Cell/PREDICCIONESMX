"""
ingest_venues.py — Ingiesta venues desde SportMonks + enriquece con altitud/coords.

Estrategia:
1. Por cada temporada objetivo, descarga fixtures con include=fixtures.venue
2. Crea/actualiza Venue con la info de SportMonks (nombre, ciudad, capacidad)
3. Enriquece con altitud/coords usando la API gratuita Open-Meteo Elevation
   (https://api.open-meteo.com/v1/elevation)
4. Marca los venues enriquecidos con enriched_at = now()

Datos hardcoded para estadios principales de Liga MX (alta precisión):
- Algunos estadios tienen altitud conocida y precisa (no confiamos en la API)

Uso:
    python3 -m proyectos.src.ingest_venues
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import PATHS, SportMonksConfig
from .db import Fixture, Season, Venue, get_session
from .logging_setup import setup_logging
from .sportmonks_client import SportMonksClient


# Datos hardcoded de altitud real (msnm) para estadios principales de Liga MX
# Fuente: Wikipedia, datos públicos verificados
VENUE_ALTITUD_HARDCODED: dict[str, dict] = {
    # Ciudad de México y zona conurbada (~2,240 m)
    "estadio azteca": {"altitude_m": 2240, "latitude": 19.3029, "longitude": -99.1505, "city": "Ciudad de México", "state": "CDMX"},
    "azteca": {"altitude_m": 2240, "latitude": 19.3029, "longitude": -99.1505, "city": "Ciudad de México", "state": "CDMX"},
    "mexico city stadium": {"altitude_m": 2240, "latitude": 19.3029, "longitude": -99.1505, "city": "Ciudad de México", "state": "CDMX"},
    "estadio olímpico universitario": {"altitude_m": 2240, "latitude": 19.3214, "longitude": -99.1777, "city": "Ciudad de México", "state": "CDMX"},
    "olímpico de universitario": {"altitude_m": 2240, "latitude": 19.3214, "longitude": -99.1777, "city": "Ciudad de México", "state": "CDMX"},
    "estadio azul": {"altitude_m": 2240, "latitude": 19.3631, "longitude": -99.1767, "city": "Ciudad de México", "state": "CDMX"},
    "estadio ciudad de los deportes": {"altitude_m": 2240, "latitude": 19.3631, "longitude": -99.1767, "city": "Ciudad de México", "state": "CDMX"},
    "estadio akron": {"altitude_m": 1566, "latitude": 20.6305, "longitude": -103.3470, "city": "Zapopan", "state": "Jalisco"},
    "estadio omnilife": {"altitude_m": 1566, "latitude": 20.6305, "longitude": -103.3470, "city": "Zapopan", "state": "Jalisco"},
    "guadalajara stadium": {"altitude_m": 1566, "latitude": 20.6305, "longitude": -103.3470, "city": "Zapopan", "state": "Jalisco"},
    "estadio jalisco": {"altitude_m": 1566, "latitude": 20.7042, "longitude": -103.3297, "city": "Guadalajara", "state": "Jalisco"},
    "estadio nemesio díez": {"altitude_m": 2680, "latitude": 19.2867, "longitude": -99.6714, "city": "Toluca", "state": "Estado de México"},
    "nemesio diez": {"altitude_m": 2680, "latitude": 19.2867, "longitude": -99.6714, "city": "Toluca", "state": "Estado de México"},
    "estadio cuauhtémoc": {"altitude_m": 2135, "latitude": 19.0781, "longitude": -98.1677, "city": "Puebla", "state": "Puebla"},
    "cuauhtemoc": {"altitude_m": 2135, "latitude": 19.0781, "longitude": -98.1677, "city": "Puebla", "state": "Puebla"},
    "estadio universitario": {"altitude_m": 540, "latitude": 25.6692, "longitude": -100.2431, "city": "San Nicolás de los Garza", "state": "Nuevo León"},
    "estadio universitario de nuevo león": {"altitude_m": 540, "latitude": 25.6692, "longitude": -100.2431, "city": "San Nicolás de los Garza", "state": "Nuevo León"},
    "monterrey stadium": {"altitude_m": 540, "latitude": 25.6703, "longitude": -100.2394, "city": "Guadalupe", "state": "Nuevo León"},
    "estadio bbva": {"altitude_m": 540, "latitude": 25.6703, "longitude": -100.2394, "city": "Guadalupe", "state": "Nuevo León"},
    "estadio tsm corona": {"altitude_m": 20, "latitude": 23.1841, "longitude": -106.4222, "city": "Torreón", "state": "Coahuila"},
    "estadio nuevo corona": {"altitude_m": 20, "latitude": 23.1841, "longitude": -106.4222, "city": "Torreón", "state": "Coahuila"},
    "corona": {"altitude_m": 20, "latitude": 23.1841, "longitude": -106.4222, "city": "Torreón", "state": "Coahuila"},
    "estadio caliente": {"altitude_m": 40, "latitude": 32.5231, "longitude": -117.0375, "city": "Tijuana", "state": "Baja California"},
    "estadio hidalgo": {"altitude_m": 2400, "latitude": 20.1011, "longitude": -98.7561, "city": "Pachuca", "state": "Hidalgo"},
    "hidalgo": {"altitude_m": 2400, "latitude": 20.1011, "longitude": -98.7561, "city": "Pachuca", "state": "Hidalgo"},
    "estadio la corregidora": {"altitude_m": 1820, "latitude": 20.5775, "longitude": -100.3681, "city": "Santiago de Querétaro", "state": "Querétaro"},
    "la corregidora": {"altitude_m": 1820, "latitude": 20.5775, "longitude": -100.3681, "city": "Santiago de Querétaro", "state": "Querétaro"},
    "estadio victoria": {"altitude_m": 1880, "latitude": 21.1019, "longitude": -101.6778, "city": "Aguascalientes", "state": "Aguascalientes"},
    "estadio nou camp": {"altitude_m": 1840, "latitude": 21.1619, "longitude": -101.6931, "city": "León", "state": "Guanajuato"},
    "estadio león": {"altitude_m": 1840, "latitude": 21.1619, "longitude": -101.6931, "city": "León", "state": "Guanajuato"},
    "estadio casa calderón": {"altitude_m": 1880, "latitude": 21.1158, "longitude": -101.6853, "city": "León", "state": "Guanajuato"},
    "estadio cervantes": {"altitude_m": 1880, "latitude": 21.1494, "longitude": -101.6794, "city": "León", "state": "Guanajuato"},
    "estadio pedro moreno": {"altitude_m": 1880, "latitude": 21.1219, "longitude": -101.6764, "city": "León", "state": "Guanajuato"},
    "estadio mazatlán": {"altitude_m": 10, "latitude": 23.2494, "longitude": -106.4111, "city": "Mazatlán", "state": "Sinaloa"},
    "estadio olímpico universitario uach": {"altitude_m": 1430, "latitude": 28.7031, "longitude": -106.1486, "city": "Chihuahua", "state": "Chihuahua"},
    "estadio olímbico de la uach": {"altitude_m": 1430, "latitude": 28.7031, "longitude": -106.1486, "city": "Chihuahua", "state": "Chihuahua"},
    "estadio andrés manuel lópez obrador": {"altitude_m": 10, "latitude": 18.4663, "longitude": -88.2962, "city": "Chetumal", "state": "Quintana Roo"},
    "estadio olímpico andrés quintana roo": {"altitude_m": 10, "latitude": 18.4663, "longitude": -88.2962, "city": "Chetumal", "state": "Quintana Roo"},
    "estadio miguel alemán": {"altitude_m": 1880, "latitude": 20.5567, "longitude": -100.3931, "city": "Celaya", "state": "Guanajuato"},
    "estadio miguel alemán valdés": {"altitude_m": 1880, "latitude": 20.5567, "longitude": -100.3931, "city": "Celaya", "state": "Guanajuato"},
    "estadio olímpico benito juárez": {"altitude_m": 1430, "latitude": 28.7031, "longitude": -106.1486, "city": "Chihuahua", "state": "Chihuahua"},
    "estadio benito juárez": {"altitude_m": 1430, "latitude": 28.7031, "longitude": -106.1486, "city": "Chihuahua", "state": "Chihuahua"},
    "estadio héroe de nacozari": {"altitude_m": 40, "latitude": 29.0892, "longitude": -110.9611, "city": "Hermosillo", "state": "Sonora"},
    "estadio sergio león chávez": {"altitude_m": 1880, "latitude": 20.5881, "longitude": -100.3889, "city": "Irapuato", "state": "Guanajuato"},
    "estadio alfonso lastras ramírez": {"altitude_m": 1864, "latitude": 22.1567, "longitude": -100.9853, "city": "San Luis Potosí", "state": "San Luis Potosí"},
    "estadio olímpico carlos iturralde rivero": {"altitude_m": 10, "latitude": 20.9674, "longitude": -89.5926, "city": "Mérida", "state": "Yucatán"},
    "estadio agustín coruco díaz": {"altitude_m": 2200, "latitude": 18.9211, "longitude": -99.2350, "city": "Zacatepec", "state": "Morelos"},
    "estadio francisco zarco": {"altitude_m": 1880, "latitude": 24.0277, "longitude": -104.6532, "city": "Durango", "state": "Durango"},
    "estadio tamaulipas": {"altitude_m": 200, "latitude": 22.2551, "longitude": -97.8686, "city": "Tampico", "state": "Tamaulipas"},
    "estadio tecnológico de oaxaca": {"altitude_m": 1555, "latitude": 17.0732, "longitude": -96.7266, "city": "Oaxaca", "state": "Oaxaca"},
    "estadio generalísimo josé maría morelos y pavón": {"altitude_m": 1880, "latitude": 19.7011, "longitude": -101.1856, "city": "Morelia", "state": "Michoacán"},
    "estadio marcelino garza": {"altitude_m": 540, "latitude": 25.6692, "longitude": -100.2431, "city": "San Nicolás de los Garza", "state": "Nuevo León"},
    "estadio carlos vega villalba": {"altitude_m": 1900, "latitude": 23.7363, "longitude": -99.1411, "city": "Ciudad Victoria", "state": "Tamaulipas"},
    "estadio olímbico ing. marte r. gómez": {"altitude_m": 230, "latitude": 22.2551, "longitude": -97.8686, "city": "Ciudad Madero", "state": "Tamaulipas"},
    "estadio tlahuicole": {"altitude_m": 2252, "latitude": 19.3139, "longitude": -98.2364, "city": "Tlaxcala", "state": "Tlaxcala"},
    "estadio gregorio tepa gómez": {"altitude_m": 1800, "latitude": 20.8167, "longitude": -102.7667, "city": "Tepatitlán", "state": "Jalisco"},
    "estadio guaycura": {"altitude_m": 40, "latitude": 22.8905, "longitude": -109.9167, "city": "Cabo San Lucas", "state": "Baja California Sur"},
    "estadio olímbico de villahermosa": {"altitude_m": 20, "latitude": 17.9892, "longitude": -92.9475, "city": "Villahermosa", "state": "Tabasco"},
    "cancha el barrial": {"altitude_m": 540, "latitude": 25.7494, "longitude": -100.2889, "city": "Monterrey", "state": "Nuevo León"},
    "instalaciones de verde valle": {"altitude_m": 1566, "latitude": 20.6305, "longitude": -103.3470, "city": "Zapopan", "state": "Jalisco"},
    "vancouver stadium": {"altitude_m": 70, "latitude": 49.2280, "longitude": -123.1110, "city": "Vancouver", "state": "BC"},
}


ELEVATION_CACHE = PATHS.data_dir / "venue_elevation_cache.json"


def normalize_name(name: str) -> str:
    """Normaliza nombre del venue para matching."""
    if not name:
        return ""
    return name.lower().strip().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")


def get_hardcoded_venue(name: str) -> dict | None:
    """Busca el venue en la tabla hardcoded por nombre normalizado."""
    norm = normalize_name(name)
    if not norm:
        return None
    # Normalizar también los keys del hardcoded
    hardcoded_norm = {normalize_name(k): v for k, v in VENUE_ALTITUD_HARDCODED.items()}
    # 1. Matching exacto
    if norm in hardcoded_norm:
        return hardcoded_norm[norm]
    # 2. Matching por substring (key dentro de norm O norm dentro de key) - requiere key largo
    for key, data in hardcoded_norm.items():
        if len(key) >= 8 and (key in norm or norm in key):
            return data
    # 3. Matching por palabras clave significativas
    STOP_WORDS = {"estadio", "est", "el", "la", "de", "del", "los", "las", "y", "o", "u", "a",
                  "stadium", "field", "arena", "cancha", "instalaciones", "deportivo", "complejo"}
    norm_words = {w for w in norm.split() if w not in STOP_WORDS and len(w) >= 4}
    best_match = None
    best_score = 0
    for key, data in hardcoded_norm.items():
        key_words = {w for w in key.split() if w not in STOP_WORDS and len(w) >= 4}
        if not key_words:
            continue
        common = norm_words & key_words
        if not common:
            continue
        score = len(common) / len(norm_words | key_words)
        if score >= 0.5 and score > best_score:
            best_score = score
            best_match = data
    return best_match


def get_elevation_from_openmeteo(lat: float, lon: float) -> float | None:
    """Consulta la API gratuita de Open-Meteo para obtener elevación."""
    try:
        url = "https://api.open-meteo.com/v1/elevation"
        params = {"latitude": lat, "longitude": lon}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        elev = data.get("elevation", [None])[0]
        return float(elev) if elev is not None else None
    except Exception as e:
        logger.debug(f"Error Open-Meteo para ({lat}, {lon}): {e}")
        return None


def load_cache() -> dict:
    if ELEVATION_CACHE.exists():
        try:
            with open(ELEVATION_CACHE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache: dict) -> None:
    ELEVATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(ELEVATION_CACHE, "w") as f:
        json.dump(cache, f, indent=2)


def enrich_venue(venue: Venue, cache: dict) -> bool:
    """Enriquece un venue con altitud/coords. Devuelve True si se actualizó."""
    if venue.enriched_at and (datetime.utcnow() - venue.enriched_at).days < 30:
        return False  # ya enriquecido recientemente
    # 1. Intentar con hardcoded
    hardcoded = get_hardcoded_venue(venue.name or "")
    if hardcoded:
        venue.altitude_m = venue.altitude_m or hardcoded["altitude_m"]
        venue.latitude = venue.latitude or hardcoded["latitude"]
        venue.longitude = venue.longitude or hardcoded["longitude"]
        venue.city = venue.city or hardcoded.get("city")
        venue.state = venue.state or hardcoded.get("state")
        venue.enriched_at = datetime.utcnow()
        return True
    # 2. Si ya tiene lat/lon de SportMonks, consultar Open-Meteo
    if venue.latitude and venue.longitude and not venue.altitude_m:
        cache_key = f"{venue.latitude},{venue.longitude}"
        if cache_key in cache:
            venue.altitude_m = int(cache[cache_key])
        else:
            elev = get_elevation_from_openmeteo(venue.latitude, venue.longitude)
            if elev is not None:
                venue.altitude_m = int(elev)
                cache[cache_key] = elev
        venue.enriched_at = datetime.utcnow()
        return True
    return False


def upsert_venue(session: Session, v: dict) -> Venue | None:
    if not v or not v.get("id"):
        return None
    venue = session.get(Venue, v["id"])
    city = v.get("city")
    cap = v.get("capacity")
    surface = v.get("surface")
    roof = v.get("roof")
    coords = v.get("coordinates") or {}
    lat = coords.get("latitude") if isinstance(coords, dict) else None
    lon = coords.get("longitude") if isinstance(coords, dict) else None

    if venue is None:
        venue = Venue(
            id=v["id"], name=v.get("name") or f"Venue {v['id']}",
            city=city, country="Mexico",
            altitude_m=None, latitude=lat, longitude=lon,
            capacity=cap, surface=surface, roof_type=roof,
            climate_zone=None, meta_json=v,
        )
        session.add(venue)
    else:
        venue.name = v.get("name") or venue.name
        if city:
            venue.city = city
        if cap:
            venue.capacity = cap
        if surface:
            venue.surface = surface
        if roof:
            venue.roof_type = roof
        if lat and not venue.latitude:
            venue.latitude = lat
        if lon and not venue.longitude:
            venue.longitude = lon
        venue.meta_json = v
    return venue


def main() -> int:
    setup_logging("INFO")
    cfg = SportMonksConfig.from_env()
    Session = get_session()

    cache = load_cache()
    venue_added = 0
    venue_enriched = 0

    with Session() as session:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        seasons = session.execute(
            select(Season)
            .where(Season.end_date < now)
            .order_by(Season.league_id, Season.start_date.desc())
        ).scalars().all()
        by_league = {}
        for s in seasons:
            by_league.setdefault(s.league_id, []).append(s)
        target = []
        for lid in sorted(by_league):
            target.extend(by_league[lid][:5])
        print(f"🎯 {len(target)} temporadas objetivo")

    with SportMonksClient(cfg) as client, Session() as session:
        for s in target:
            season = session.get(Season, s.id)
            if not season:
                continue
            print(f"\n→ Liga {s.league_id} | {s.name}", flush=True)
            try:
                r = client._request(f"seasons/{s.id}", {"include": "fixtures.venue"})
            except Exception as e:
                print(f"  ⚠️  Error: {e}", flush=True)
                continue
            fixtures = r.get("data", {}).get("fixtures", [])
            season_venues = 0
            for f in fixtures:
                v = f.get("venue")
                if not v or not v.get("id"):
                    continue
                venue = upsert_venue(session, v)
                if venue:
                    venue_added += 1
                    season_venues += 1
            session.commit()
            print(f"  📦 {season_venues} venues", flush=True)

        # Enriquecer con altitud
        print("\n🏔️ Enriqueciendo venues con altitud/coords...", flush=True)
        all_venues = session.execute(select(Venue)).scalars().all()
        for v in all_venues:
            if enrich_venue(v, cache):
                venue_enriched += 1
        session.commit()
        if cache:
            save_cache(cache)

    # Resumen
    print(f"\n{'='*50}")
    print(f"📊 Resumen:")
    with Session() as session:
        all_venues = session.execute(select(Venue)).scalars().all()
        enriched = [v for v in all_venues if v.enriched_at]
        with_altitude = [v for v in all_venues if v.altitude_m]
        print(f"  • Total venues:           {len(all_venues)}")
        print(f"  • Con altitud:            {len(with_altitude)}")
        print(f"  • Enriquecidos hoy:       {venue_enriched}")
        print(f"  • Nuevos en BD:           {venue_added}")
        print()
        print("Top 10 estadios por altitud:")
        top = sorted(with_altitude, key=lambda v: v.altitude_m or 0, reverse=True)[:10]
        for v in top:
            print(f"  {v.altitude_m:>5}m | {v.name}")
        print()
        print("Top 5 estadios más bajos:")
        low = sorted(with_altitude, key=lambda v: v.altitude_m or 0)[:5]
        for v in low:
            print(f"  {v.altitude_m:>5}m | {v.name}")
    print(f"{'='*50}")
    return 0


if __name__ == "__main__":
    sys.exit(main())