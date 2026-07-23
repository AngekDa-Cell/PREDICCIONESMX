"""
ingest_h2h.py — Ingester de historial head-to-head (H2H) entre equipos desde SportMonks.

Estrategia:
1. Para cada equipo de Liga MX, descarga todos los fixtures finalizados via
   `teams/{id}?include=fixtures.participants` (1 request por equipo).
2. Almacena en BD local (tabla `team_h2h_raw`) cada fixture con score y participantes.
3. Calcula H2H agregado por par de equipos y lo cachea en `team_h2h_cache`.

Ventajas:
- Cache persistente → no rehace el cruce cada partido.
- Aísla la dependencia de tokens para que el predict_match() no falle si SportMonks cae.
- Permite re-correr con `--refresh` para actualizar.
- BUG FIX 2026-07-23: antes el modelo decía "no hay H2H" para Atlante vs América, ahora
  sí tenemos histórico de SportMonks (5+ años por equipo).

Uso:
    python3 scripts/ingest_h2h.py --refresh     # full re-download (~18 requests)
    python3 scripts/ingest_h2h.py --incremental # solo temporadas nuevas
    python3 scripts/ingest_h2h.py --dry-run     # calcularía pero no guarda

Performance:
- 1 request por equipo. ~18 equipos top Liga MX → ~18 requests, <1 minuto.
- Si solo querés velocidad: usar BD local (H2H desde tabla `fixtures` de los últimos 5 años).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Repo paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from src.config import SportMonksConfig  # noqa: E402
from src.sportmonks_client import SportMonksClient  # noqa: E402

DB = "/workspace/proyectos/data/predictions_mx.db"


# ─────────────────────────────────────────────────────────────────────────────
# Tablas
# ─────────────────────────────────────────────────────────────────────────────

def ensure_tables(conn: sqlite3.Connection) -> None:
    """Crea las tablas team_h2h_raw y team_h2h_cache si no existen."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS team_h2h_raw (
            fixture_id INTEGER PRIMARY KEY,
            league_id INTEGER,
            season_id INTEGER,
            starting_at TEXT,
            home_team_id INTEGER,
            away_team_id INTEGER,
            home_score INTEGER,
            away_score INTEGER,
            source TEXT,
            ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_h2h_raw_teams
            ON team_h2h_raw(home_team_id, away_team_id);

        CREATE TABLE IF NOT EXISTS team_h2h_cache (
            team_a_id INTEGER NOT NULL,
            team_b_id INTEGER NOT NULL,
            n_matches INTEGER NOT NULL DEFAULT 0,
            team_a_wins INTEGER DEFAULT 0,
            team_b_wins INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            team_a_goals INTEGER DEFAULT 0,
            team_b_goals INTEGER DEFAULT 0,
            team_a_home_wins INTEGER DEFAULT 0,
            team_a_away_wins INTEGER DEFAULT 0,
            most_recent TEXT,
            oldest_match TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (team_a_id, team_b_id)
        );

        CREATE INDEX IF NOT EXISTS idx_h2h_cache_b
            ON team_h2h_cache(team_b_id);
    """)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Ingestión: descargar fixtures por equipo y guardar crudos
# ─────────────────────────────────────────────────────────────────────────────

def fetch_team_fixtures(client: SportMonksClient, team_id: int) -> list[dict]:
    """
    Descarga TODOS los fixtures finalizados de un equipo via SportMonks.
    Endpoint: /teams/{id}?include=fixtures.participants;fixtures.scores
    
    SportMonks v3 quirks (verificado 2026-07-23):
    - Este endpoint IGNORA el parámetro `page` y devuelve TODOS los fixtures en una sola llamada.
    - Solo respeta `cursor` para paginación si supera el límite interno.
    - Para ~750 fixtures (Atlante histórico) devuelve todo en 1 request.
    - Para ~3500 fixtures (América) puede necesitar cursor (paginado por cursor).
    
    Estrategia: pedir page=1 SIN cursor. Si la respuesta NO trae cursor, terminamos.
    Si trae cursor, iteramos.
    """
    all_fixtures = []
    seen_ids = set()
    cursor = None
    MAX_PAGES = 20  # safety

    for page_num in range(1, MAX_PAGES + 1):
        params = {
            "include": "fixtures.participants;fixtures.scores",
            "per_page": 200,  # pedir muchos para reducir calls
        }
        if cursor is not None:
            params["cursor"] = cursor
            params.pop("page", None)
        else:
            params["page"] = page_num

        try:
            resp = client._request(f"teams/{team_id}", params)
        except Exception as e:
            print(f"  ⚠️  Team {team_id} page {page_num} error: {e}")
            break

        data = resp.get("data", {})
        fixtures = data.get("fixtures", []) or []
        if not fixtures:
            break

        new_in_page = 0
        for fx in fixtures:
            if fx.get("id") not in seen_ids:
                seen_ids.add(fx.get("id"))
                all_fixtures.append(fx)
                new_in_page += 1
        # Si todos los items de esta página ya los tenemos, cortamos
        if new_in_page == 0:
            break

        pagination = resp.get("pagination", {}) or {}
        next_cursor_raw = pagination.get("next_cursor")
        has_more = pagination.get("has_more")

        if next_cursor_raw:
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(next_cursor_raw)
            qs = parse_qs(parsed.query)
            cursor = qs.get("cursor", [None])[0]
            if not cursor:
                break
        elif has_more is False:
            break
        elif pagination.get("count", 0) < params["per_page"]:
            break
        # Si no hay cursor ni has_more False, volveremos con page+1 (algunos endpoints lo requieren)

    return all_fixtures


def ingest_team(client: SportMonksClient, conn: sqlite3.Connection, team_id: int, refresh: bool = False) -> int:
    """
    Descarga y guarda fixtures de un equipo. Devuelve cuántos insertó/actualizó.
    """
    existing = conn.execute(
        "SELECT COUNT(*) FROM team_h2h_raw WHERE home_team_id = ? OR away_team_id = ?",
        (team_id, team_id)
    ).fetchone()[0]

    if existing > 0 and not refresh:
        # Ya tenemos datos. Solo actualizamos fixtures nuevos (mayor fixture_id).
        max_id_existing = conn.execute("""
            SELECT COALESCE(MAX(fixture_id), 0) FROM team_h2h_raw
            WHERE home_team_id = ? OR away_team_id = ?
        """, (team_id, team_id)).fetchone()[0]
    else:
        max_id_existing = 0

    fixtures = fetch_team_fixtures(client, team_id)
    new_count = 0
    skipped = 0

    for fx in fixtures:
        fx_id = fx.get("id")
        if not fx_id or fx_id <= max_id_existing:
            continue

        # Solo fixtures finalizados con score (state_id=5 = FT)
        state_id = fx.get("state_id")
        if state_id != 5:
            skipped += 1
            continue

        # IDs de los participantes (con location)
        participants = fx.get("participants", [])
        home_id = away_id = None
        for p in participants:
            meta = p.get("meta", {}) or {}
            loc = meta.get("location")
            if loc == "home":
                home_id = p.get("id")
            elif loc == "away":
                away_id = p.get("id")

        if not (home_id and away_id):
            skipped += 1
            continue

        # Extraer scores finales del array `scores` (filtro description='CURRENT', type_id=1525)
        scores = fx.get("scores", [])
        home_score = away_score = None
        for s in scores:
            desc = s.get("description", "")
            if desc == "CURRENT" or s.get("type_id") == 1525:
                pid = s.get("participant_id")
                goals = s.get("score", {}).get("goals")
                if pid == home_id and home_score is None:
                    home_score = goals
                elif pid == away_id and away_score is None:
                    away_score = goals

        # Fallback: usar meta.winner + meta.location si no hay scores
        if home_score is None or away_score is None:
            # Al menos verificar que hay un ganador declarado
            winner_map = {p.get("id"): p.get("meta", {}).get("winner") for p in participants}
            if winner_map.get(home_id) is not None or winner_map.get(away_id) is not None:
                # Tenemos al ganador, inferir resultado pero perder score exacto
                # Marcar como 0-0 placeholder para que después se pueda detectar
                home_score = 0 if winner_map.get(home_id) == True else (
                    0 if winner_map.get(home_id) == False else None
                )
                if winner_map.get(home_id) and not winner_map.get(away_id):
                    home_score = 1
                    away_score = 0
                elif winner_map.get(away_id) and not winner_map.get(home_id):
                    home_score = 0
                    away_score = 1
                elif winner_map.get(home_id) == False and winner_map.get(away_id) == False:
                    home_score = 0
                    away_score = 0

        if home_score is None or away_score is None:
            skipped += 1
            continue

        try:
            conn.execute("""
                INSERT OR REPLACE INTO team_h2h_raw
                  (fixture_id, league_id, season_id, starting_at,
                   home_team_id, away_team_id, home_score, away_score, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'sportmonks')
            """, (
                fx_id,
                fx.get("league_id"),
                fx.get("season_id"),
                fx.get("starting_at"),
                home_id, away_id,
                home_score, away_score,
            ))
            new_count += 1
        except Exception as e:
            print(f"  ⚠️  Insert error fixture {fx_id}: {e}")

    conn.commit()
    if skipped > 0:
        print(f"    (skipped {skipped} sin scores/estado) ", end="")
    return new_count


# ─────────────────────────────────────────────────────────────────────────────
# Construcción del cache H2H desde los raw
# ─────────────────────────────────────────────────────────────────────────────

def recompute_h2h_cache(conn: sqlite3.Connection) -> int:
    """
    Recorre team_h2h_raw y construye team_h2h_cache agregado por par de equipos.
    """
    # Borrar cache actual
    conn.execute("DELETE FROM team_h2h_cache")

    # Traer todos los partidos finalizados
    rows = conn.execute("""
        SELECT home_team_id, away_team_id, home_score, away_score, starting_at
        FROM team_h2h_raw
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        ORDER BY starting_at DESC
    """).fetchall()

    # Aggregate
    h2h = defaultdict(lambda: {
        "n": 0, "a_wins": 0, "b_wins": 0, "draws": 0,
        "a_gf": 0, "b_gf": 0,
        "a_home_wins": 0, "a_away_wins": 0,
        "most_recent": None, "oldest": None,
    })

    for home_id, away_id, hs, as_, date in rows:
        # Ordenar el par canónicamente (menor ID primero)
        a, b = sorted([home_id, away_id])
        key = (a, b)

        entry = h2h[key]
        entry["n"] += 1

        # Actualizar fechas
        if entry["most_recent"] is None or (date and date > entry["most_recent"]):
            entry["most_recent"] = date
        if entry["oldest"] is None or (date and date < entry["oldest"]):
            entry["oldest"] = date

        # Scores: a_wins siempre desde perspectiva del ID menor
        if home_id == a:
            # a es home
            entry["a_gf"] += hs
            entry["b_gf"] += as_
            if hs > as_:
                entry["a_wins"] += 1
                entry["a_home_wins"] += 1
            elif hs < as_:
                entry["b_wins"] += 1
            else:
                entry["draws"] += 1
        else:
            # a es away, b es home
            entry["a_gf"] += as_  # a_mark goals = away_score
            entry["b_gf"] += hs
            if as_ > hs:
                entry["a_wins"] += 1
                entry["a_away_wins"] += 1
            elif as_ < hs:
                entry["b_wins"] += 1
            else:
                entry["draws"] += 1

    # Insertar
    for (a, b), e in h2h.items():
        conn.execute("""
            INSERT INTO team_h2h_cache
              (team_a_id, team_b_id, n_matches,
               team_a_wins, team_b_wins, draws,
               team_a_goals, team_b_goals,
               team_a_home_wins, team_a_away_wins,
               most_recent, oldest_match)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            a, b, e["n"],
            e["a_wins"], e["b_wins"], e["draws"],
            e["a_gf"], e["b_gf"],
            e["a_home_wins"], e["a_away_wins"],
            e["most_recent"], e["oldest"],
        ))

    conn.commit()
    return len(h2h)


# ─────────────────────────────────────────────────────────────────────────────
# Lookup function (usado por get_head_to_head)
# ─────────────────────────────────────────────────────────────────────────────

def lookup_h2h(
    conn: sqlite3.Connection,
    team_a: int,
    team_b: int,
    limit: int = 10,
) -> dict | None:
    """
    Devuelve stats H2H agregadas desde cache.
    Retorna None si no hay cache (caller debe caer al fallback de BD local).
    """
    a, b = sorted([team_a, team_b])
    row = conn.execute("""
        SELECT n_matches, team_a_wins, team_b_wins, draws,
               team_a_goals, team_b_goals, team_a_home_wins, team_a_away_wins,
               most_recent, oldest_match
        FROM team_h2h_cache
        WHERE team_a_id = ? AND team_b_id = ?
    """, (a, b)).fetchone()
    if not row or row[0] == 0:
        return None

    n, aw, bw, dr, agf, aga, ahw, aaw, mr, oldest = row
    return {
        "total": n,
        "a_wins": aw,
        "b_wins": bw,
        "draws": dr,
        "a_goals": agf,
        "b_goals": aga,
        "a_win_rate": aw / n if n else 0.0,
        "draw_rate": dr / n if n else 0.0,
        "a_home_wins": ahw,
        "a_away_wins": aaw,
        "most_recent": mr,
        "oldest": oldest,
        "source": "sportmonks_cache",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="H2H ingestor desde SportMonks")
    parser.add_argument("--refresh", action="store_true",
                        help="Forzar re-download completo de todos los equipos")
    parser.add_argument("--dry-run", action="store_true",
                        help="Calcula stats pero no guarda en BD")
    parser.add_argument("--team-id", type=int,
                        help="Solo procesar este equipo (debug)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB)
    ensure_tables(conn)

    cfg = SportMonksConfig.from_env()
    client = SportMonksClient(cfg)

    # Obtener equipos activos
    if args.team_id:
        team_ids = [args.team_id]
    else:
        team_ids = [r[0] for r in conn.execute("""
            SELECT DISTINCT home_team_id FROM fixtures WHERE league_id IN (743, 749)
            UNION SELECT DISTINCT away_team_id FROM fixtures WHERE league_id IN (743, 749)
            ORDER BY 1
        """).fetchall()]

    print(f"=== H2H INGEST ===")
    print(f"Equipos a procesar: {len(team_ids)}")
    print(f"Refresh: {args.refresh}")
    print()

    total_new = 0
    t_start = time.monotonic()

    for i, tid in enumerate(team_ids):
        team_name = conn.execute("SELECT name FROM teams WHERE id = ?", (tid,)).fetchone()
        team_name = team_name[0] if team_name else f"Team {tid}"
        print(f"[{i+1}/{len(team_ids)}] {team_name} (id={tid})...", end=" ", flush=True)

        if args.dry_run:
            fixtures = fetch_team_fixtures(client, tid)
            print(f"{len(fixtures)} fixtures (no guardados)")
        else:
            new_n = ingest_team(client, conn, tid, refresh=args.refresh)
            total_new += new_n
            print(f"OK ({new_n} nuevos)")

    elapsed = time.monotonic() - t_start
    print(f"\nDescarga: {total_new} fixtures nuevos en {elapsed:.1f}s")

    if not args.dry_run:
        print("\nRecalculando cache H2H agregado...")
        n_pairs = recompute_h2h_cache(conn)
        print(f"  {n_pairs} pares únicos en cache")

    # Test
    print("\n=== TESTS ===")
    test_pairs = [
        (7023, 2687, "Atlante vs América"),
        (7023, 2626, "Atlante vs Cruz Azul"),
        (2626, 2687, "Cruz Azul vs América"),
    ]
    for a, b, label in test_pairs:
        h2h = lookup_h2h(conn, a, b)
        if h2h:
            print(f"  {label}: {h2h['total']} partidos | "
                  f"A:{h2h['a_wins']} D:{h2h['draws']} B:{h2h['b_wins']} | "
                  f"Goles {h2h['a_goals']}-{h2h['b_goals']} | "
                  f"Más reciente: {h2h['most_recent']}")
        else:
            print(f"  {label}: sin datos en cache")

    conn.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
