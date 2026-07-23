"""
features.py — Cómputo de features derivados para predicción de partidos.

Todas las funciones reciben team_id, opponent_id, fixture_date y db connection.
Computan features en tiempo de ejecución (no rely en tablas pre-pobladas).
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date(val) -> Optional[datetime]:
    """Parsea varios formatos de fecha que puede devolver SQLite."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TEAM FORM — últimos N partidos (W/D/L + goals)
# ─────────────────────────────────────────────────────────────────────────────

def get_team_form(
    conn: sqlite3.Connection,
    team_id: int,
    before_date: Optional[str] = None,
    n: int = 5,
    league_id: int = 743
) -> Dict[str, Any]:
    """
    Retorna la forma del equipo en los últimos N partidos jugados
    antes de before_date. Solo cuenta partidos de liga (league_id).

    Returns:
        {
            'matches': n,
            'wins': int, 'draws': int, 'losses': int,
            'goals_for': int, 'goals_against': int,
            'points': int,          # 3*wins + draws
            'win_rate': float,
            'avg_goals_for': float,
            'avg_goals_against': float,
            'clean_sheets': int,
            'failed_to_score': int,
            'form_str': str,       # 'W-D-L-W-W'
            'momentum': float,    # puntos por partido (0-3)
        }
    """
    if before_date:
        date_filter = "AND f.starting_at < :before_date"
        params = {"team_id": team_id, "league_id": league_id, "before_date": before_date}
    else:
        date_filter = ""
        params = {"team_id": team_id, "league_id": league_id}

    query = f"""
        SELECT
            f.id, f.home_team_id, f.away_team_id,
            f.home_score, f.away_score,
            f.starting_at
        FROM fixtures f
        WHERE f.league_id = :league_id
          AND f.home_score IS NOT NULL
          AND f.away_score IS NOT NULL
          AND (f.home_team_id = :team_id OR f.away_team_id = :team_id)
          {date_filter}
        ORDER BY f.starting_at DESC
        LIMIT :n
    """
    params["n"] = n

    rows = conn.execute(query, params).fetchall()

    if not rows:
        return {
            'matches': 0, 'wins': 0, 'draws': 0, 'losses': 0,
            'goals_for': 0, 'goals_against': 0, 'points': 0,
            'win_rate': 0.0, 'avg_goals_for': 0.0, 'avg_goals_against': 0.0,
            'clean_sheets': 0, 'failed_to_score': 0,
            'form_str': '', 'momentum': 0.0,
        }

    wins = draws = losses = gf = ga = cs = ft_score = 0
    form_parts = []

    for row in rows:
        _, home_id, away_id, home_score, away_score = row[:5]

        if home_id == team_id:
            gf += home_score
            ga += away_score
            if home_score > away_score:
                wins += 1; form_parts.append('W')
            elif home_score == away_score:
                draws += 1; form_parts.append('D')
            else:
                losses += 1; form_parts.append('L')
            if away_score == 0:
                cs += 1
            if home_score == 0:
                ft_score += 1
        else:
            gf += away_score
            ga += home_score
            if away_score > home_score:
                wins += 1; form_parts.append('W')
            elif away_score == home_score:
                draws += 1; form_parts.append('D')
            else:
                losses += 1; form_parts.append('L')
            if home_score == 0:
                cs += 1
            if away_score == 0:
                ft_score += 1

    matches = wins + draws + losses
    points = 3 * wins + draws
    momentum = points / matches if matches > 0 else 0.0

    return {
        'matches': matches,
        'wins': wins, 'draws': draws, 'losses': losses,
        'goals_for': gf, 'goals_against': ga,
        'points': points,
        'win_rate': wins / matches if matches > 0 else 0.0,
        'avg_goals_for': gf / matches if matches > 0 else 0.0,
        'avg_goals_against': ga / matches if matches > 0 else 0.0,
        'clean_sheets': cs,
        'failed_to_score': ft_score,
        'form_str': '-'.join(form_parts),
        'momentum': momentum,
    }


def get_head_to_head(
    conn: sqlite3.Connection,
    team_a: int,
    team_b: int,
    limit: int = 10,
    league_id: int = 743
) -> Dict[str, Any]:
    """Historial directo entre dos equipos.

    BUG FIX 2026-07-23: ahora consulta primero el cache de H2H de SportMonks
    (tabla team_h2h_cache con ~939 pares y miles de fixtures del histórico)
    y SOLO si no hay datos, hace fallback a la BD local. Esto soluciona el
    problema de "no hay H2H" para partidos como Atlante vs América donde los
    equipos no se han enfrentado en los últimos 5 años pero sí tienen
    18+ partidos en el histórico completo.

    Returns: dict con total, a_wins, b_wins, draws, a_win_rate, draw_rate, etc.
             Si source='sportmonks_cache', los datos son de SportMonks (10-20 años).
             Si source='local_db', los datos son de la BD local (5 años).
             Si total=0, no hay datos de ningún origen.
    """
    # ────────────────────────────────────────────────────────────────────
    # PASO 1: Buscar en cache SportMonks (PRIORIDAD)
    # ────────────────────────────────────────────────────────────────────
    try:
        # team_h2h_cache tiene pares ordenados por ID menor primero
        a_sorted, b_sorted = sorted([team_a, team_b])
        cache_row = conn.execute("""
            SELECT n_matches, team_a_wins, team_b_wins, draws,
                   team_a_goals, team_b_goals, team_a_home_wins, team_a_away_wins
            FROM team_h2h_cache
            WHERE team_a_id = ? AND team_b_id = ?
        """, (a_sorted, b_sorted)).fetchone()

        if cache_row and cache_row[0] > 0:
            n, awins, bwins, draws, agf, aga, ahw, aaw = cache_row
            # Mapear de vuelta al orden original team_a vs team_b
            if a_sorted == team_a:
                # team_a == team_a_sorted (es el menor)
                return {
                    'total': n,
                    'a_wins': awins, 'b_wins': bwins, 'draws': draws,
                    'a_goals': agf, 'b_goals': aga,
                    'a_win_rate': awins / n if n else 0.0,
                    'draw_rate': draws / n if n else 0.0,
                    'a_home_wins': ahw,
                    'a_away_wins': aaw,
                    'source': 'sportmonks_cache',
                }
            else:
                # team_a == team_b_sorted (es el mayor)
                return {
                    'total': n,
                    'a_wins': bwins, 'b_wins': awins, 'draws': draws,
                    'a_goals': aga, 'b_goals': agf,
                    'a_win_rate': bwins / n if n else 0.0,
                    'draw_rate': draws / n if n else 0.0,
                    # En este caso ahw = team_b_sorted_home_wins (no team_a)
                    'a_home_wins': n - ahw - awins,  # resto = team_b como away wins
                    'a_away_wins': awins - ahw,
                    'source': 'sportmonks_cache',
                }
    except Exception:
        # Si la tabla no existe (BD vieja), cae al fallback
        pass

    # ────────────────────────────────────────────────────────────────────
    # PASO 2: Fallback a BD local (5 años)
    # ────────────────────────────────────────────────────────────────────
    query = """
        SELECT f.home_team_id, f.away_team_id, f.home_score, f.away_score
        FROM fixtures f
        WHERE f.league_id = :league_id
          AND f.home_score IS NOT NULL
          AND ((f.home_team_id = :a AND f.away_team_id = :b)
               OR (f.home_team_id = :b AND f.away_team_id = :a))
        ORDER BY f.starting_at DESC
        LIMIT :limit
    """
    rows = conn.execute(query, {"a": team_a, "b": team_b, "league_id": league_id, "limit": limit}).fetchall()

    a_wins = b_wins = draws = a_gf = a_ga = 0
    for home_id, away_id, home_score, away_score in rows:
        if home_id == team_a:
            a_gf += home_score; a_ga += away_score
            if home_score > away_score:
                a_wins += 1
            elif home_score == away_score:
                draws += 1
            else:
                b_wins += 1
        else:
            a_gf += away_score; a_ga += home_score
            if away_score > home_score:
                a_wins += 1
            elif away_score == home_score:
                draws += 1
            else:
                b_wins += 1

    total = a_wins + b_wins + draws
    return {
        'total': total,
        'a_wins': a_wins, 'b_wins': b_wins, 'draws': draws,
        'a_goals': a_gf, 'b_goals': a_ga,
        'a_win_rate': a_wins / total if total > 0 else 0.0,
        'draw_rate': draws / total if total > 0 else 0.0,
        'source': 'local_db',
    }


# ─────────────────────────────────────────────────────────────────────────────
# ALTITUDE ADVANTAGE
# ─────────────────────────────────────────────────────────────────────────────

# Altitude thresholds (in meters)
ALTITUDE_HIGH = 2000
ALTITUDE_VERY_HIGH = 2400

# Coastal/low altitude teams (baseline)
LOW_ALTITUDE_TEAMS = {
    'Monterrey': 540, 'Pumas UNAM': 540, 'Tigres UANL': 540,
    'Santos Laguna': 20, 'Tijuana': 40,
}


def get_altitude_advantage(
    conn: sqlite3.Connection,
    home_team_id: int,
    away_team_id: int
) -> Dict[str, Any]:
    """
    Retorna la ventaja de altitud del local.
    En CDMX/Pachuca/Toluca (2400m+) los equipos visitantes
    suelen fatigarse más rápido.
    """
    row = conn.execute(
        "SELECT altitude_m FROM venues WHERE id = (SELECT venue_id FROM teams WHERE id = ?)",
        (home_team_id,)
    ).fetchone()
    home_altitude = row[0] if row else 0

    row = conn.execute(
        "SELECT altitude_m FROM venues WHERE id = (SELECT venue_id FROM teams WHERE id = ?)",
        (away_team_id,)
    ).fetchone()
    away_altitude = row[0] if row else 0

    diff = home_altitude - away_altitude

    # Clasificación
    if home_altitude >= ALTITUDE_VERY_HIGH:
        classification = "very_high"
    elif home_altitude >= ALTITUDE_HIGH:
        classification = "high"
    elif home_altitude < 100:
        classification = "sea_level"
    else:
        classification = "normal"

    return {
        'home_altitude': home_altitude,
        'away_altitude': away_altitude,
        'altitude_diff': diff,
        'classification': classification,
        # Score heurístico 0-1 (mayor = más ventaja local por altitud)
        'altitude_score': min(diff / 2400, 1.0) if diff > 0 else 0.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# REST DAYS
# ─────────────────────────────────────────────────────────────────────────────

def get_rest_days(
    conn: sqlite3.Connection,
    team_id: int,
    fixture_date: str,
    league_id: int = 743
) -> int:
    """Días de descanso desde el último partido del equipo."""
    row = conn.execute("""
        SELECT starting_at FROM fixtures
        WHERE league_id = :league_id
          AND (home_team_id = :team_id OR away_team_id = :team_id)
          AND starting_at < :fixture_date
          AND home_score IS NOT NULL
        ORDER BY starting_at DESC LIMIT 1
    """, {"team_id": team_id, "league_id": league_id, "fixture_date": fixture_date}).fetchone()

    if not row:
        return 99  # Sin partido previo = descansado

    last_date = _parse_date(row[0])
    if last_date is None:
        return 99

    try:
        # fixture_date puede venir como string ISO
        if isinstance(fixture_date, str):
            current = datetime.fromisoformat(fixture_date.replace('Z', '+00:00'))
        else:
            current = fixture_date
        delta = (current - last_date).total_seconds() / 86400
        return int(delta)
    except Exception:
        return 99


def rest_days_advantage(
    conn: sqlite3.Connection,
    home_team_id: int,
    away_team_id: int,
    fixture_date: str
) -> Dict[str, Any]:
    """Ventaja por días de descanso."""
    home_rest = get_rest_days(conn, home_team_id, fixture_date)
    away_rest = get_rest_days(conn, away_team_id, fixture_date)
    diff = home_rest - away_rest

    # Más de 7 días de descanso puede significar rust
    home_rusty = 1 if home_rest > 10 else 0
    away_rusty = 1 if away_rest > 10 else 0

    return {
        'home_rest_days': home_rest,
        'away_rest_days': away_rest,
        'rest_diff': diff,
        'home_rusty': home_rusty,
        'away_rusty': away_rusty,
        # Score: positivo = ventaja local
        'rest_score': (home_rest - away_rest) / 7.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COACH / DT PRESSURE
# ─────────────────────────────────────────────────────────────────────────────

def get_coach_pressure(
    conn: sqlite3.Connection,
    team_id: int,
    current_season_id: int
) -> Dict[str, Any]:
    """
    Retorna presión sobre el DT del equipo.
    Usa coach_tenures: winless streak, games sin ganar, etc.

    Si no hay datos de W/D/L, estimamos por racha de resultados recientes.
    """
    # Buscar el tenure actual del equipo en la temporada
    tenure = conn.execute("""
        SELECT id, coach_id, games_managed, wins, draws, losses, is_current
        FROM coach_tenures
        WHERE team_id = ? AND season_id = ? AND is_current = 1
        ORDER BY start_date DESC LIMIT 1
    """, (team_id, current_season_id)).fetchone()

    if tenure and tenure[3] is not None:
        games, wins, draws, losses = tenure[2], tenure[3], tenure[4], tenure[5]
        if games and games > 0:
            win_rate = wins / games
            points_per_game = (3 * wins + draws) / games
            # Winless streak
            winless = games - wins  # aproximación simple
            pressure_index = min(winless / 10, 1.0)  # 0-1, mayor = más presión
            return {
                'coach_id': tenure[1],
                'games_managed': games,
                'wins': wins, 'draws': draws, 'losses': losses,
                'win_rate': win_rate,
                'points_per_game': points_per_game,
                'winless_streak': winless,
                'pressure_index': pressure_index,
                'data_source': 'tenures',
            }

    # Fallback: estimar por forma reciente del equipo
    # Últimos 8 partidos como proxy
    form = get_team_form(conn, team_id, n=8)
    if form['matches'] >= 3:
        winless = form['matches'] - form['wins']
        # Más presión si no gana en 4+ partidos
        pressure_index = min(winless / 6, 1.0)
        return {
            'coach_id': None,
            'games_managed': form['matches'],
            'wins': form['wins'], 'draws': form['draws'], 'losses': form['losses'],
            'win_rate': form['win_rate'],
            'points_per_game': form['momentum'],
            'winless_streak': winless,
            'pressure_index': pressure_index,
            'data_source': 'form_proxy',
        }

    return {
        'coach_id': None,
        'games_managed': 0, 'wins': 0, 'draws': 0, 'losses': 0,
        'win_rate': 0.0, 'points_per_game': 0.0,
        'winless_streak': 0, 'pressure_index': 0.0,
        'data_source': 'unknown',
    }


# ─────────────────────────────────────────────────────────────────────────────
# HOME / AWAY SPLIT
# ─────────────────────────────────────────────────────────────────────────────

def get_home_away_split(
    conn: sqlite3.Connection,
    team_id: int,
    before_date: Optional[str] = None,
    n: int = 20,
    league_id: int = 743
) -> Dict[str, Any]:
    """Rendimiento local vs visitante del equipo."""
    if before_date:
        date_filter = "AND f.starting_at < :before_date"
        params = {"team_id": team_id, "league_id": league_id, "before_date": before_date, "n": n}
    else:
        date_filter = ""
        params = {"team_id": team_id, "league_id": league_id, "n": n}

    home_q = f"""
        SELECT f.home_score, f.away_score FROM fixtures f
        WHERE f.league_id = :league_id AND f.home_team_id = :team_id
          AND f.home_score IS NOT NULL {date_filter}
        ORDER BY f.starting_at DESC LIMIT :n
    """
    away_q = f"""
        SELECT f.home_score, f.away_score FROM fixtures f
        WHERE f.league_id = :league_id AND f.away_team_id = :team_id
          AND f.home_score IS NOT NULL {date_filter}
        ORDER BY f.starting_at DESC LIMIT :n
    """

    def _split_stats(q, params, is_home):
        rows = conn.execute(q, params).fetchall()
        if not rows:
            return {
                'matches': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                'gf': 0, 'ga': 0,
                'win_rate': 0.0,
                'avg_gf': 0.0,
                'avg_ga': 0.0,
            }
        w = d = l = gf = ga = 0
        for r in rows:
            home_s, away_s = r
            team_goals = home_s if is_home else away_s
            opp_goals = away_s if is_home else home_s
            gf += team_goals
            ga += opp_goals
            if team_goals > opp_goals:
                w += 1
            elif team_goals == opp_goals:
                d += 1
            else:
                l += 1
        m = len(rows)
        return {
            'matches': m, 'wins': w, 'draws': d, 'losses': l,
            'gf': gf, 'ga': ga,
            'win_rate': w / m if m > 0 else 0.0,
            'avg_gf': gf / m if m > 0 else 0.0,
            'avg_ga': ga / m if m > 0 else 0.0,
        }

    home = _split_stats(home_q, params, True)
    away = _split_stats(away_q, params, {**params, "n": n})

    return {
        'home': home, 'away': away,
        # Ventaja local = home_win_rate - away_win_rate
        'home_advantage': home['win_rate'] - away['win_rate'],
        'home_goal_diff': home['avg_gf'] - home['avg_ga'],
        'away_goal_diff': away['avg_gf'] - away['avg_ga'],
    }


# ─────────────────────────────────────────────────────────────────────────────
# SEASON CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

def get_season_context(
    conn: sqlite3.Connection,
    team_id: int,
    season_id: int
) -> Dict[str, Any]:
    """Contexto del equipo EN la temporada actual."""
    rows = conn.execute("""
        SELECT f.home_team_id, f.away_team_id, f.home_score, f.away_score
        FROM fixtures f
        WHERE f.season_id = ?
          AND f.league_id = 743
          AND (f.home_team_id = ? OR f.away_team_id = ?)
          AND f.home_score IS NOT NULL
        ORDER BY f.starting_at
    """, (season_id, team_id, team_id)).fetchall()

    if not rows:
        return {'played': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                'goals_for': 0, 'goals_against': 0, 'points': 0, 'position': None}

    w = d = l = gf = ga = 0
    for home_id, away_id, hs, as_ in rows:
        if home_id == team_id:
            gf += hs; ga += as_
            if hs > as_: w += 1
            elif hs == as_: d += 1
            else: l += 1
        else:
            gf += as_; ga += hs
            if as_ > hs: w += 1
            elif as_ == hs: d += 1
            else: l += 1

    played = len(rows)
    points = 3 * w + d

    return {
        'played': played, 'wins': w, 'draws': d, 'losses': l,
        'goals_for': gf, 'goals_against': ga,
        'goal_diff': gf - ga,
        'points': points,
        'win_rate': w / played if played > 0 else 0.0,
        'avg_points_per_game': points / played if played > 0 else 0.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ATTACK / DEFENSE STRENGTH (para Poisson)
# ─────────────────────────────────────────────────────────────────────────────

def get_attack_defense_strength(
    conn: sqlite3.Connection,
    team_id: int,
    season_id: int,
    n: int = 30,
    league_id: int = 743
) -> Dict[str, float]:
    """
    Returns attack_strength y defense_strength relativos.
    Promedio de goles anotados/Recibidos vs promedio de la liga.
    > 1.0 = mejor que promedio; < 1.0 = peor.
    """
    # Promedio de la liga
    rows = conn.execute("""
        SELECT f.home_score, f.away_score
        FROM fixtures f
        WHERE f.season_id = :season_id
          AND f.league_id = :league_id
          AND f.home_score IS NOT NULL
        LIMIT 500
    """, {"season_id": season_id, "league_id": league_id}).fetchall()

    if not rows:
        return {
            'attack_strength': 1.0, 'defense_strength': 1.0,
            'def_weakness': 1.0, 'team_avg_gf': 0.0,
            'team_avg_ga': 0.0, 'league_avg_gf': 1.5, 'sample_size': 0,
        }

    all_gf = [r[0] for r in rows] + [r[1] for r in rows]
    league_avg_gf = sum(all_gf) / len(all_gf) if all_gf else 1.5

    # Partidos como local
    home_matches = conn.execute("""
        SELECT f.home_score, f.away_score FROM fixtures f
        WHERE f.season_id = :season_id AND f.league_id = :league_id
          AND f.home_score IS NOT NULL AND f.home_team_id = :team_id
        LIMIT :n
    """, {"season_id": season_id, "league_id": league_id, "team_id": team_id, "n": n}).fetchall()
    team_gf_list = [r[0] for r in home_matches]
    team_ga_list = [r[1] for r in home_matches]

    # Partidos como visitante
    away_matches = conn.execute("""
        SELECT f.home_score, f.away_score FROM fixtures f
        WHERE f.season_id = :season_id AND f.league_id = :league_id
          AND f.home_score IS NOT NULL AND f.away_team_id = :team_id
        LIMIT :n
    """, {"season_id": season_id, "league_id": league_id, "team_id": team_id, "n": n}).fetchall()
    for r in away_matches:
        team_gf_list.append(r[1])   # goals scored = away_score
        team_ga_list.append(r[0])   # goals conceded = home_score

    team_avg_gf = sum(team_gf_list) / len(team_gf_list) if team_gf_list else 0.0
    team_avg_ga = sum(team_ga_list) / len(team_ga_list) if team_ga_list else 0.0

    return {
        'attack_strength': team_avg_gf / league_avg_gf if league_avg_gf > 0 else 1.0,
        'defense_strength': team_avg_ga / league_avg_gf if league_avg_gf > 0 else 1.0,
        'def_weakness': team_avg_ga / league_avg_gf if league_avg_gf > 0 else 1.0,
        'team_avg_gf': round(team_avg_gf, 3),
        'team_avg_ga': round(team_avg_ga, 3),
        'league_avg_gf': round(league_avg_gf, 3),
        'sample_size': len(team_gf_list),
    }




# ─────────────────────────────────────────────────────────────────────────────
# TRAVEL DISTANCE — distancia recorrida por el equipo en últimos 7 días
# ─────────────────────────────────────────────────────────────────────────────

import math

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos coordenadas."""
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def get_travel_distance(
    conn: sqlite3.Connection,
    team_id: int,
    fixture_date: str,
    league_id: int = 743
) -> Dict[str, Any]:
    """
    Distancia total recorrida por el equipo en los últimos 7 días.
    Calculada como suma de distancias entre venues consecutivos.

    Returns:
        {
            'distance_7d_km': float,
            'games_7d': int,
            'longest_leg_km': float,  # viaje más largo
            'classification': str,   # 'low' | 'normal' | 'high'
        }
    """
    rows = conn.execute("""
        SELECT v.latitude, v.longitude
        FROM fixtures f
        LEFT JOIN teams th ON f.home_team_id = th.id
        LEFT JOIN teams ta ON f.away_team_id = ta.id
        LEFT JOIN venues vh ON th.venue_id = vh.id
        LEFT JOIN venues va ON ta.venue_id = va.id
        LEFT JOIN venues v ON (f.home_team_id = :team_id AND v.id = vh.id)
                              OR (f.away_team_id = :team_id AND v.id = va.id)
        WHERE f.league_id = :league_id
          AND (f.home_team_id = :team_id OR f.away_team_id = :team_id)
          AND f.starting_at < :fixture_date
          AND f.starting_at >= datetime(:fixture_date, '-7 days')
          AND f.home_score IS NOT NULL
        ORDER BY f.starting_at DESC
    """, {"team_id": team_id, "league_id": league_id, "fixture_date": fixture_date}).fetchall()

    coords = [(r[0], r[1]) for r in rows if r[0] is not None and r[1] is not None]
    
    if len(coords) < 2:
        return {
            'distance_7d_km': 0.0,
            'games_7d': len(coords),
            'longest_leg_km': 0.0,
            'classification': 'low',
        }

    # Calcular distancia total recorrida
    total_km = 0.0
    max_leg = 0.0
    for i in range(len(coords) - 1):
        d = haversine_km(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1])
        total_km += d
        max_leg = max(max_leg, d)

    if total_km < 500:
        cls = 'low'
    elif total_km < 1500:
        cls = 'normal'
    elif total_km < 3000:
        cls = 'high'
    else:
        cls = 'extreme'

    return {
        'distance_7d_km': round(total_km, 1),
        'games_7d': len(coords),
        'longest_leg_km': round(max_leg, 1),
        'classification': cls,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE CONGESTION — partidos en últimos 7 días
# ─────────────────────────────────────────────────────────────────────────────

def get_fixture_congestion(
    conn: sqlite3.Connection,
    team_id: int,
    fixture_date: str,
    league_id: int = 743
) -> Dict[str, Any]:
    """
    Cuenta de partidos en últimos 7 días y 14 días.
    Útil para detectar fatigue por calendar congestion.

    Returns:
        {
            'games_7d': int,
            'games_14d': int,
            'high_congestion': bool,  # 3+ en 7d
            'moderate_congestion': bool,  # 2 en 7d
        }
    """
    g7 = conn.execute("""
        SELECT COUNT(*) FROM fixtures
        WHERE league_id = :league_id
          AND (home_team_id = :team_id OR away_team_id = :team_id)
          AND starting_at < :fixture_date
          AND starting_at >= datetime(:fixture_date, '-7 days')
          AND home_score IS NOT NULL
    """, {"team_id": team_id, "league_id": league_id, "fixture_date": fixture_date}).fetchone()[0]

    g14 = conn.execute("""
        SELECT COUNT(*) FROM fixtures
        WHERE league_id = :league_id
          AND (home_team_id = :team_id OR away_team_id = :team_id)
          AND starting_at < :fixture_date
          AND starting_at >= datetime(:fixture_date, '-14 days')
          AND home_score IS NOT NULL
    """, {"team_id": team_id, "league_id": league_id, "fixture_date": fixture_date}).fetchone()[0]

    return {
        'games_7d': g7,
        'games_14d': g14,
        'high_congestion': g7 >= 3,
        'moderate_congestion': g7 == 2,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COACH TENURE DAYS — tiempo del DT en el cargo
# ─────────────────────────────────────────────────────────────────────────────

def get_coach_tenure_days(
    conn: sqlite3.Connection,
    team_id: int,
    fixture_date: str,
) -> Dict[str, Any]:
    """
    Calcula los días que el DT actual lleva en el cargo.
    
    Detecta:
    - 'new' (0-30 días): potential bounce o instability
    - 'developing' (30-180 días): establishing system
    - 'established' (>180 días): system estable
    """
    tenure = conn.execute("""
        SELECT id, start_date, end_date, is_current, games_managed, wins, draws, losses
        FROM coach_tenures
        WHERE team_id = ?
          AND (end_date IS NULL OR end_date > ?)
          AND start_date <= ?
        ORDER BY is_current DESC, start_date DESC LIMIT 1
    """, (team_id, fixture_date, fixture_date)).fetchone()

    if not tenure or not tenure[1]:
        return {
            'tenure_days': None,
            'phase': 'unknown',
            'games_managed': 0,
            'win_rate': 0.0,
            'is_new_coach': False,
        }

    tenure_id, start_date, end_date, is_current, games, w, d, l = tenure

    try:
        start_dt = datetime.strptime(str(start_date)[:10], '%Y-%m-%d')
        current_dt = datetime.strptime(str(fixture_date)[:10], '%Y-%m-%d')
        days = (current_dt - start_dt).days
    except (ValueError, TypeError):
        return {
            'tenure_days': None,
            'phase': 'unknown',
            'games_managed': 0,
            'win_rate': 0.0,
            'is_new_coach': False,
        }

    if days < 30:
        phase = 'new'
        is_new = True
    elif days < 180:
        phase = 'developing'
        is_new = False
    else:
        phase = 'established'
        is_new = False

    win_rate = (w or 0) / games if games and games > 0 else 0.0

    return {
        'tenure_days': days,
        'phase': phase,
        'games_managed': games or 0,
        'win_rate': round(win_rate, 3),
        'is_new_coach': is_new,
        'start_date': str(start_date)[:10] if start_date else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EXPONENTIAL FORM — forma con ponderación exponencial por recencia
# ─────────────────────────────────────────────────────────────────────────────

def get_exponential_form(
    conn: sqlite3.Connection,
    team_id: int,
    before_date: Optional[str] = None,
    decay: float = 0.85,  # peso de cada partido anterior (más reciente = más peso)
    max_n: int = 10,
    league_id: int = 743
) -> Dict[str, Any]:
    """
    Forma ponderada exponencialmente. Partido más reciente pesa 1.0,
    segundo más reciente decay, tercero decay^2, etc.
    
    Returns: weighted stats
    """
    if before_date:
        date_filter = "AND f.starting_at < :before_date"
        params = {"team_id": team_id, "league_id": league_id, "before_date": before_date}
    else:
        date_filter = ""
        params = {"team_id": team_id, "league_id": league_id}

    query = f"""
        SELECT f.home_team_id, f.away_team_id, f.home_score, f.away_score
        FROM fixtures f
        WHERE f.league_id = :league_id
          AND f.home_score IS NOT NULL
          AND (f.home_team_id = :team_id OR f.away_team_id = :team_id)
          {date_filter}
        ORDER BY f.starting_at DESC LIMIT :max_n
    """
    params["max_n"] = max_n
    rows = conn.execute(query, params).fetchall()

    if not rows:
        return {
            'matches': 0, 'weighted_points': 0.0, 'total_weight': 0.0,
            'weighted_gf': 0.0, 'weighted_ga': 0.0,
            'weighted_win_rate': 0.0, 'momentum_score': 0.0,
        }

    weighted_points = 0.0
    weighted_gf = 0.0
    weighted_ga = 0.0
    weighted_wins = 0.0
    total_weight = 0.0

    for i, (home_id, away_id, hs, as_) in enumerate(rows):
        w = decay ** i  # i=0 → 1.0, i=1 → 0.85, i=2 → 0.72...
        total_weight += w

        if home_id == team_id:
            gf, ga = hs, as_
            if hs > as_:
                points = 3; weighted_wins += w
            elif hs == as_:
                points = 1
            else:
                points = 0
        else:
            gf, ga = as_, hs
            if as_ > hs:
                points = 3; weighted_wins += w
            elif as_ == hs:
                points = 1
            else:
                points = 0

        weighted_points += points * w
        weighted_gf += gf * w
        weighted_ga += ga * w

    momentum_score = weighted_points / total_weight if total_weight > 0 else 0.0

    return {
        'matches': len(rows),
        'weighted_points': round(weighted_points, 2),
        'total_weight': round(total_weight, 3),
        'weighted_gf': round(weighted_gf, 2),
        'weighted_ga': round(weighted_ga, 2),
        'weighted_win_rate': round(weighted_wins / total_weight, 3) if total_weight > 0 else 0.0,
        'momentum_score': round(momentum_score, 3),  # 0-3 como puntos por partido ponderado
    }


# ─────────────────────────────────────────────────────────────────────────────
# MATCH WEATHER (Fase 6) — clima del partido desde Open-Meteo
# ─────────────────────────────────────────────────────────────────────────────

def get_match_weather(
    conn: sqlite3.Connection,
    fixture_id: int,
) -> Dict[str, Any]:
    """
    Obtiene el clima del partido desde la tabla match_weather.

    Returns:
        {
            'available': bool,
            'temperature_c': float | None,
            'humidity_pct': int | None,
            'wind_kph': float | None,
            'precipitation_mm': float | None,
            'conditions': str | None,  # 'seco' / 'llovizna' / 'lluvioso' / 'tormenta' / 'humedo'
            'is_extreme_heat': bool,   # temp > 32°C
            'is_wet': bool,            # precipitacion > 0.5mm
            'is_high_humidity': bool,  # humedad > 80%
        }
    """
    row = conn.execute("""
        SELECT temperature_c, feels_like_c, humidity_pct, wind_kph,
               wind_direction, precipitation_mm, conditions, cloud_cover_pct
        FROM match_weather
        WHERE fixture_id = ?
    """, (fixture_id,)).fetchone()

    if not row:
        return {
            'available': False,
            'temperature_c': None,
            'humidity_pct': None,
            'wind_kph': None,
            'precipitation_mm': None,
            'conditions': None,
            'is_extreme_heat': False,
            'is_wet': False,
            'is_high_humidity': False,
        }

    temp = row[0]
    humidity = row[2]
    wind = row[3]
    precip = row[5]
    conditions = row[6]

    return {
        'available': True,
        'temperature_c': temp,
        'humidity_pct': humidity,
        'wind_kph': wind,
        'precipitation_mm': precip,
        'conditions': conditions,
        'is_extreme_heat': temp is not None and temp > 32,
        'is_wet': precip is not None and precip > 0.5,
        'is_high_humidity': humidity is not None and humidity > 80,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITE MOMENTUM (Fase 6) — combina forma reciente + exponencial
# ─────────────────────────────────────────────────────────────────────────────

def get_composite_momentum(
    conn: sqlite3.Connection,
    team_id: int,
    before_date: Optional[str] = None,
    n_recent: int = 5,
    decay: float = 0.85,
    max_n: int = 10,
    league_id: int = 743
) -> Dict[str, Any]:
    """
    Momentum compuesto: combina forma reciente con forma exponencial ponderada.

    Tres señales:
    1. **Recent momentum** (W-D-L últimos 5): momentum crudo por partido (0-3)
    2. **Exponential momentum** (decay 0.85, últimos 10): ponderado por recencia
    3. **Trend**: mejora/empeora vs partidos anteriores (-1, 0, +1)

    Más robusto que cada feature individual porque:
    - Recent captura "qué tan bien está ahora"
    - Exponential captura "tendencia sostenida"
    - Trend captura "dirección del cambio"

    Returns:
        {
            'recent_momentum': float,      # 0-3 (puntos por partido, últimos 5)
            'exponential_momentum': float, # 0-3 (ponderado exponencial, últimos 10)
            'composite_score': float,      # 0-3 (combinación ponderada)
            'trend': int,                  # -1 (empeorando), 0 (igual), +1 (mejorando)
            'consistency': float,          # 0-1 (qué tan consistente es la forma)
            'n_matches': int,
        }
    """
    # Forma reciente (W-D-L simples)
    recent = get_team_form(conn, team_id, before_date, n_recent, league_id)
    # Forma exponencial
    exp = get_exponential_form(conn, team_id, before_date, decay, max_n, league_id)

    recent_momentum = recent.get('momentum', 0.0)
    exponential_momentum = exp.get('momentum_score', 0.0)

    # Composite: 40% recent + 60% exponential (pondera más la tendencia sostenida)
    composite = recent_momentum * 0.4 + exponential_momentum * 0.6

    # Trend: diferencia entre últimos 3 partidos y anteriores
    trend = _calculate_trend(conn, team_id, before_date, league_id)

    # Consistency: 1 - coefficient_of_variation de points/match
    consistency = _calculate_consistency(conn, team_id, before_date, league_id)

    return {
        'recent_momentum': round(recent_momentum, 3),
        'exponential_momentum': round(exponential_momentum, 3),
        'composite_score': round(composite, 3),
        'trend': trend,
        'consistency': round(consistency, 3),
        'n_matches': recent.get('matches', 0),
    }


def _calculate_trend(
    conn: sqlite3.Connection,
    team_id: int,
    before_date: Optional[str] = None,
    league_id: int = 743,
) -> int:
    """
    Calcula tendencia: +1 si mejorando, -1 si empeorando, 0 si igual.

    Compara últimos 3 partidos vs los 3 anteriores.
    """
    if before_date:
        date_filter = "AND f.starting_at < :before_date"
        params = {"team_id": team_id, "league_id": league_id, "before_date": before_date}
    else:
        date_filter = ""
        params = {"team_id": team_id, "league_id": league_id}

    rows = conn.execute(f"""
        SELECT f.home_team_id, f.away_team_id, f.home_score, f.away_score
        FROM fixtures f
        WHERE f.league_id = :league_id
          AND f.home_score IS NOT NULL
          AND (f.home_team_id = :team_id OR f.away_team_id = :team_id)
          {date_filter}
        ORDER BY f.starting_at DESC LIMIT 6
    """, params).fetchall()

    if len(rows) < 6:
        return 0

    def points_per_match(rs):
        total = 0
        for home_id, away_id, hs, as_ in rs:
            if home_id == team_id:
                if hs > as_:
                    total += 3
                elif hs == as_:
                    total += 1
            else:
                if as_ > hs:
                    total += 3
                elif as_ == hs:
                    total += 1
        return total / len(rs) if rs else 0

    last_3 = rows[:3]
    prev_3 = rows[3:6]

    last_3_ppm = points_per_match(last_3)
    prev_3_ppm = points_per_match(prev_3)

    diff = last_3_ppm - prev_3_ppm
    if diff > 0.3:
        return 1   # mejorando
    elif diff < -0.3:
        return -1  # empeorando
    return 0       # igual


def _calculate_consistency(
    conn: sqlite3.Connection,
    team_id: int,
    before_date: Optional[str] = None,
    league_id: int = 743,
) -> float:
    """
    Mide consistencia de la forma: 1 - coefficient_of_variation.

    1.0 = totalmente consistente (todos los partidos con misma performance)
    0.0 = totalmente inconsistente
    """
    if before_date:
        date_filter = "AND f.starting_at < :before_date"
        params = {"team_id": team_id, "league_id": league_id, "before_date": before_date}
    else:
        date_filter = ""
        params = {"team_id": team_id, "league_id": league_id}

    rows = conn.execute(f"""
        SELECT f.home_team_id, f.away_team_id, f.home_score, f.away_score
        FROM fixtures f
        WHERE f.league_id = :league_id
          AND f.home_score IS NOT NULL
          AND (f.home_team_id = :team_id OR f.away_team_id = :team_id)
          {date_filter}
        ORDER BY f.starting_at DESC LIMIT 10
    """, params).fetchall()

    if len(rows) < 3:
        return 0.5  # default neutral

    # Puntos por partido
    points_per_match = []
    for home_id, away_id, hs, as_ in rows:
        if home_id == team_id:
            p = 3 if hs > as_ else 1 if hs == as_ else 0
        else:
            p = 3 if as_ > hs else 1 if as_ == hs else 0
        points_per_match.append(p)

    # Calcular CV
    mean = sum(points_per_match) / len(points_per_match)
    variance = sum((p - mean) ** 2 for p in points_per_match) / len(points_per_match)
    std = variance ** 0.5

    if mean == 0:
        return 0.5

    cv = std / mean
    # Mapear CV [0, 2] → consistency [1, 0]
    consistency = max(0.0, 1.0 - cv / 2.0)
    return consistency


# ─────────────────────────────────────────────────────────────────────────────
# LOAD MX CALIBRATION COEFFICIENTS
# ─────────────────────────────────────────────────────────────────────────────

def load_mx_coefficients() -> Dict[str, Any]:
    """Carga coeficientes calibrados con datos Liga MX."""
    import json
    from pathlib import Path
    path = Path(__file__).parent / "mx_coefficients.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# REFEREE BIAS (Fase 9 — árbitro del partido)
# ─────────────────────────────────────────────────────────────────────────────


def get_referee_bias(
    conn: sqlite3.Connection,
    fixture_id: Optional[int] = None,
    referee_id: Optional[int] = None,
    home_team_id: Optional[int] = None,
    away_team_id: Optional[int] = None,
    fixture_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Devuelve el sesgo histórico del árbitro del partido.

    El bias_score es home_win_rate - 0.5:
      - positivo (>+0.05):倾向于local (más victorias locales)
      - negativo (<-0.05):倾向于visitante
      - cerca de 0: neutral

    Si no hay árbitro o tiene <30 partidos, devuelve neutral con available=False.

    Args:
        conn: conexión sqlite
        fixture_id: ID del fixture (busca el main referee)
        referee_id: ID directo del árbitro (alternativo)
        home_team_id, away_team_id, fixture_date: trio alternativo para
            encontrar el referee cuando no hay fixture_id (ej. en backtests)

    Returns:
        Dict con keys: available, referee_id, name, games, bias_score,
                       tendency, home_win_rate, draw_rate, away_win_rate
    """
    from .referee_bias import (
        RefereeStats,
        MIN_GAMES_FOR_STATS,
        MAX_BIAS_ABS,
    )

    rid: int | None = None
    if referee_id is not None:
        rid = referee_id
    elif fixture_id is not None:
        c = conn.cursor()
        c.execute(
            "SELECT referee_id FROM referee_assignments WHERE fixture_id = ? AND type_id = 6",
            (fixture_id,),
        )
        row = c.fetchone()
        rid = row[0] if row else None
    elif home_team_id is not None and away_team_id is not None and fixture_date is not None:
        # Lookup por equipos + fecha (tolera ±1 día para diferencias de timezone)
        c = conn.cursor()
        c.execute(
            """
            SELECT ra.referee_id FROM referee_assignments ra
            JOIN fixtures f ON f.id = ra.fixture_id
            WHERE ra.type_id = 6
              AND f.home_team_id = ?
              AND f.away_team_id = ?
              AND f.starting_at BETWEEN ? AND datetime(?, '+1 day')
            LIMIT 1
            """,
            (home_team_id, away_team_id, fixture_date, fixture_date),
        )
        row = c.fetchone()
        rid = row[0] if row else None

    if rid is None:
        return {
            "available": False,
            "referee_id": None,
            "name": None,
            "games": 0,
            "bias_score": 0.0,
            "tendency": "unknown",
            "home_win_rate": None,
            "draw_rate": None,
            "away_win_rate": None,
            "is_reliable": False,
        }

    # Calcular stats desde la BD (sin caché para usar fecha del fixture)
    # En backtests in-sample esto es información del futuro. Para evitar leakage,
    # sólo usamos partidos anteriores al fixture_date si se pasa.
    c = conn.cursor()
    # Buscar partidos anteriores del referee (si fixture_id fue dado, usar su fecha)
    if fixture_id is not None:
        c.execute("SELECT starting_at FROM fixtures WHERE id = ?", (fixture_id,))
        row = c.fetchone()
        cutoff_date = row[0] if row else None
    else:
        cutoff_date = None

    if cutoff_date:
        c.execute(
            """
            SELECT
                COUNT(DISTINCT f.id),
                AVG(CASE WHEN f.home_score > f.away_score THEN 1.0 ELSE 0.0 END),
                AVG(CASE WHEN f.home_score = f.away_score THEN 1.0 ELSE 0.0 END),
                AVG(CASE WHEN f.home_score < f.away_score THEN 1.0 ELSE 0.0 END)
            FROM referee_assignments ra
            JOIN fixtures f ON f.id = ra.fixture_id
            WHERE ra.type_id = 6
              AND ra.referee_id = ?
              AND f.starting_at < ?
              AND f.home_score IS NOT NULL
            """,
            (rid, cutoff_date),
        )
    else:
        c.execute(
            """
            SELECT
                COUNT(DISTINCT f.id),
                AVG(CASE WHEN f.home_score > f.away_score THEN 1.0 ELSE 0.0 END),
                AVG(CASE WHEN f.home_score = f.away_score THEN 1.0 ELSE 0.0 END),
                AVG(CASE WHEN f.home_score < f.away_score THEN 1.0 ELSE 0.0 END)
            FROM referee_assignments ra
            JOIN fixtures f ON f.id = ra.fixture_id
            WHERE ra.type_id = 6
              AND ra.referee_id = ?
              AND f.home_score IS NOT NULL
            """,
            (rid,),
        )

    row = c.fetchone()
    if row is None or row[0] is None or row[0] == 0:
        return {
            "available": False,
            "referee_id": rid,
            "name": None,
            "games": 0,
            "bias_score": 0.0,
            "tendency": "unknown",
            "home_win_rate": None,
            "draw_rate": None,
            "away_win_rate": None,
            "is_reliable": False,
        }

    games, hr, dr, ar = row
    games = int(games)
    # Get name
    c.execute("SELECT COALESCE(common_name, full_name) FROM referees WHERE id = ?", (rid,))
    name_row = c.fetchone()
    name = name_row[0] if name_row else f"Referee {rid}"

    bias = (hr or 0.5) - 0.5
    # Cap bias al máximo permitido
    bias = max(-MAX_BIAS_ABS, min(MAX_BIAS_ABS, bias))

    tendency = "neutral"
    if games >= MIN_GAMES_FOR_STATS:
        if bias > 0.05:
            tendency = "home-favored"
        elif bias < -0.05:
            tendency = "away-favored"

    return {
        "available": games > 0,
        "referee_id": rid,
        "name": name,
        "games": games,
        "bias_score": round(bias, 4),
        "tendency": tendency,
        "home_win_rate": round(hr, 4) if hr is not None else None,
        "draw_rate": round(dr, 4) if dr is not None else None,
        "away_win_rate": round(ar, 4) if ar is not None else None,
        "is_reliable": games >= MIN_GAMES_FOR_STATS,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE RATIO (Fase 9 — asistencia del público vs capacidad)
# ─────────────────────────────────────────────────────────────────────────────


def get_attendance_ratio(
    conn: sqlite3.Connection,
    fixture_id: Optional[int] = None,
    home_team_id: Optional[int] = None,
    fixture_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Devuelve el ratio de asistencia del local (attendance / venue_capacity).

    El dato viene de ESPN API scrapeado en `ingest_attendance.py`.

    Args:
        conn: conexión sqlite
        fixture_id: ID del fixture (preferido)
        home_team_id + fixture_date: lookup alternativo

    Returns:
        Dict con keys:
          - available: bool (True si hay dato)
          - attendance: int (asistencia absoluta) o None
          - capacity: int (capacidad del venue) o None
          - ratio: float (0.0 a 1.0+) o None
          - capacity_factor: 'small' (<20k), 'medium' (20-35k), 'large' (>35k)
          - sold_out: bool (ratio >= 0.95)
    """
    if fixture_id is not None:
        row = conn.execute(
            """
            SELECT f.attendance, v.capacity
            FROM fixtures f
            LEFT JOIN venues v ON v.id = f.venue_id
            WHERE f.id = ?
            """,
            (fixture_id,),
        ).fetchone()
    elif home_team_id is not None and fixture_date is not None:
        # Lookup alternativo
        row = conn.execute(
            """
            SELECT f.attendance, v.capacity
            FROM fixtures f
            LEFT JOIN venues v ON v.id = f.venue_id
            WHERE f.home_team_id = ?
              AND f.starting_at BETWEEN datetime(?, '-1 day') AND datetime(?, '+1 day')
            LIMIT 1
            """,
            (home_team_id, fixture_date, fixture_date),
        ).fetchone()
    else:
        return {"available": False, "attendance": None, "capacity": None, "ratio": None,
                "capacity_factor": "unknown", "sold_out": False}

    if row is None or row[0] is None or row[1] is None:
        return {"available": False, "attendance": None, "capacity": None, "ratio": None,
                "capacity_factor": "unknown", "sold_out": False}

    attendance = int(row[0])
    capacity = int(row[1])
    if capacity <= 0:
        return {"available": False, "attendance": attendance, "capacity": capacity,
                "ratio": None, "capacity_factor": "unknown", "sold_out": False}

    ratio = attendance / capacity

    if capacity < 20000:
        factor = "small"
    elif capacity < 35000:
        factor = "medium"
    else:
        factor = "large"

    return {
        "available": True,
        "attendance": attendance,
        "capacity": capacity,
        "ratio": round(ratio, 4),
        "capacity_factor": factor,
        "sold_out": ratio >= 0.95,
    }


# ─────────────────────────────────────────────────────────────────────────────
# UPDATED get_full_feature_set — incluye los nuevos features
# ─────────────────────────────────────────────────────────────────────────────


NON_PLAYABLE_STATES = {
    "SUSPENDED", "POSTPONED", "CANCELLED", "AWARDED", "ABANDONED", "DELAYED"
}


def get_fixture_playable(conn: sqlite3.Connection, fixture_id: int) -> Dict[str, Any]:
    """
    Verifica si un fixture es jugable (no suspendido, cancelado, etc.).

    Returns:
        {"playable": bool, "reason": str or None, "state": str or None}
    """
    if fixture_id is None:
        return {"playable": True, "reason": None, "state": None}

    row = conn.execute(
        "SELECT state, home_score, away_score, starting_at FROM fixtures WHERE id = ?",
        (fixture_id,)
    ).fetchone()

    if row is None:
        return {"playable": True, "reason": None, "state": None}

    state = row[0]
    home_score, away_score = row[1], row[2]

    # Estado explícito no-jugable
    if state in NON_PLAYABLE_STATES:
        return {"playable": False, "reason": f"state={state}", "state": state}

    # Score 0-0 con fecha > 7 días atrás → probable suspendido
    if (
        home_score == 0
        and away_score == 0
        and home_score is not None
        and away_score is not None
    ):
        from datetime import datetime, timezone, timedelta
        try:
            kickoff = datetime.fromisoformat(str(row[3]).replace("Z", "+00:00") if row[3] else "")
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - kickoff
            if age > timedelta(days=7):
                return {"playable": False, "reason": "0-0 score after 7+ days (probable abandoned)", "state": state}
        except (ValueError, TypeError):
            pass

    return {"playable": True, "reason": None, "state": state}


def get_full_feature_set(
    conn: sqlite3.Connection,
    home_team_id: int,
    away_team_id: int,
    season_id: int,
    fixture_date: str,
    n_form: int = 5,
    fixture_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Retorna TODOS los features para el partido.
    Este es el output que consume el modelo Dixon-Coles y las heurísticas.

    Args:
        fixture_id: ID del fixture (opcional, para lookup de weather)
    """
    # Verificar si el partido es jugable (no suspendido/cancelado)
    if fixture_id is not None:
        playable = get_fixture_playable(conn, fixture_id)
        if not playable["playable"]:
            return {
                "error": playable["reason"],
                "state": playable["state"],
                "fixture_id": fixture_id,
            }

    home_form = get_team_form(conn, home_team_id, before_date=fixture_date, n=n_form)
    away_form = get_team_form(conn, away_team_id, before_date=fixture_date, n=n_form)

    home_ha = get_home_away_split(conn, home_team_id, before_date=fixture_date, n=15)
    away_ha = get_home_away_split(conn, away_team_id, before_date=fixture_date, n=15)

    altitude = get_altitude_advantage(conn, home_team_id, away_team_id)
    rest = rest_days_advantage(conn, home_team_id, away_team_id, fixture_date)
    coach_h = get_coach_pressure(conn, home_team_id, season_id)
    coach_a = get_coach_pressure(conn, away_team_id, season_id)

    h2h = get_head_to_head(conn, home_team_id, away_team_id, limit=10)

    home_season = get_season_context(conn, home_team_id, season_id)
    away_season = get_season_context(conn, away_team_id, season_id)

    # Strength para Poisson
    home_strength = get_attack_defense_strength(conn, home_team_id, season_id)
    away_strength = get_attack_defense_strength(conn, away_team_id, season_id)

    # Nuevos features (Fase 1.5 — calibración MX)
    home_travel = get_travel_distance(conn, home_team_id, fixture_date)
    away_travel = get_travel_distance(conn, away_team_id, fixture_date)
    home_cong = get_fixture_congestion(conn, home_team_id, fixture_date)
    away_cong = get_fixture_congestion(conn, away_team_id, fixture_date)
    home_coach_t = get_coach_tenure_days(conn, home_team_id, fixture_date)
    away_coach_t = get_coach_tenure_days(conn, away_team_id, fixture_date)
    home_exp = get_exponential_form(conn, home_team_id, before_date=fixture_date)
    away_exp = get_exponential_form(conn, away_team_id, before_date=fixture_date)

    return {
        'home_form': home_form,
        'away_form': away_form,
        'home_ha': home_ha,
        'away_ha': away_ha,
        'altitude': altitude,
        'rest': rest,
        'coach_home': coach_h,
        'coach_away': coach_a,
        'h2h': h2h,
        'home_season': home_season,
        'away_season': away_season,
        'home_strength': home_strength,
        'away_strength': away_strength,
        'home_travel': home_travel,
        'away_travel': away_travel,
        'home_congestion': home_cong,
        'away_congestion': away_cong,
        'home_coach_tenure': home_coach_t,
        'away_coach_tenure': away_coach_t,
        'home_exp_form': home_exp,
        'away_exp_form': away_exp,
        'home_composite_momentum': get_composite_momentum(conn, home_team_id, before_date=fixture_date),
        'away_composite_momentum': get_composite_momentum(conn, away_team_id, before_date=fixture_date),
        'weather': get_match_weather(conn, fixture_id) if fixture_id else {'available': False},
        'referee_bias': get_referee_bias(
            conn,
            fixture_id=fixture_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            fixture_date=fixture_date,
        ),
        'attendance_ratio': get_attendance_ratio(
            conn,
            fixture_id=fixture_id,
            home_team_id=home_team_id,
            fixture_date=fixture_date,
        ),
        'mx_coefficients': load_mx_coefficients(),
        'injuries': get_player_injuries_impact(conn, home_team_id, fixture_date),
        'away_injuries': get_player_injuries_impact(conn, away_team_id, fixture_date),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PLAYER INJURIES — Fase 10.5 (Plan A — ingesta ESPN API v2)
# Calcula el impacto agregado de jugadores lesionados por equipo.
# Importancia = severity × minutes_factor × position_factor
# ─────────────────────────────────────────────────────────────────────────────

# Severidad de la lesión: Out > Doubtful > Questionable > Day-To-Day > Probable
SEVERITY_FACTOR = {
    "Out": 1.00,
    "Doubtful": 0.75,
    "Questionable": 0.50,
    "Day-To-Day": 0.35,
    "Probable": 0.20,
    "": 0.0,
}

# Factor posicional: qué tanto afecta la ausencia por posición
POSITION_FACTOR = {
    "GK": 0.80, "G": 0.80, "Goalkeeper": 0.80, "Portero": 0.80,
    "D":  0.40, "DEF": 0.40, "Defender": 0.40, "Defensa": 0.40,
    "M":  0.50, "MID": 0.50, "Midfielder": 0.50, "Mediocampista": 0.50,
    "F":  0.70, "FW": 0.70, "FWD": 0.70, "Forward": 0.70, "Atacante": 0.70,
    "A":  0.65, "Attacker": 0.65,
}


def _resolve_position_factor(pos_str: str) -> float:
    """Resuelve el factor posicional desde abreviaturas o nombres."""
    if not pos_str:
        return 0.5
    pos = pos_str.strip().upper()
    if pos in POSITION_FACTOR:
        return POSITION_FACTOR[pos]
    # Substring match para casos como "Centre-Back", "Right Winger"
    for key, val in POSITION_FACTOR.items():
        if key.upper() in pos:
            return val
    return 0.5  # default si no reconocemos


def get_player_injuries_impact(
    conn: sqlite3.Connection,
    team_id: int,
    fixture_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calcula el impacto agregado de lesiones activas para un equipo en una fecha.

    Args:
        conn: SQLite connection
        team_id: ID del equipo en SportMonks
        fixture_date: fecha del partido (ISO string). Si None, usa hoy.

    Returns:
        {
            'available': bool,            # ¿hay datos de lesiones?
            'total_impact': float,        # suma de importance scores (0-N)
            'players_out': int,           # número de jugadores lesionados activos
            'key_players_out': int,       # jugadores con importance > 0.4
            'avg_severity': float,        # 0-1
            'top_injuries': [             # top 3 lesionados con detalle
                {
                    'name': str,
                    'position': str,
                    'severity': str,
                    'severity_factor': float,
                    'minutes_factor': float,
                    'position_factor': float,
                    'importance': float,   # score 0-1 (severity * minutes * position)
                    'injury_type': str,
                    'injury_date': str,
                },
                ...
            ],
            'no_data': bool,              # True si no hay lesiones registradas
        }
    """
    if fixture_date is None:
        fixture_date = datetime.now().isoformat()

    # Traer lesiones activas (sin end_date o end_date > fixture_date)
    rows = conn.execute(
        """
        SELECT
            pi.id,
            pi.player_id,
            pi.severity,
            pi.injury_type,
            pi.start_date,
            pi.meta_json,
            p.primary_position,
            p.secondary_position,
            p.full_name,
            p.common_name
        FROM player_injuries pi
        LEFT JOIN players p ON p.id = pi.player_id
        WHERE pi.team_id = ?
          AND (pi.end_date IS NULL OR pi.end_date > ?)
          AND pi.start_date <= ?
        ORDER BY pi.start_date DESC
        """,
        (team_id, fixture_date, fixture_date),
    ).fetchall()

    if not rows:
        return {
            "available": False,
            "total_impact": 0.0,
            "players_out": 0,
            "key_players_out": 0,
            "avg_severity": 0.0,
            "top_injuries": [],
            "no_data": True,
        }

    injuries = []
    for row in rows:
        inj_id, player_id, severity, injury_type, start_date, meta_json, pos_p, pos_s, full_name, common_name = row

        # Severity factor (Out=1.0, Doubtful=0.75, ...)
        sev_factor = SEVERITY_FACTOR.get(severity or "", 0.5)

        # Minutes factor: minutos/90 promedio en últimos 5 partidos del equipo.
        # NOTA: la tabla fixture_lineups puede tener minutes_played NULL si la ingesta
        # original no los guardó. En ese caso usamos is_starter como proxy:
        #   starter = 0.85 (titular habitual)
        #   no-starter = 0.30 (suplente)
        if player_id is None:
            minutes_factor = 0.5
        else:
            minutes_row = conn.execute(
                """
                SELECT AVG(fl.minutes_played) as avg_min,
                       SUM(CASE WHEN fl.is_starter=1 THEN 1 ELSE 0 END) as starts,
                       COUNT(*) as games
                FROM fixture_lineups fl
                JOIN fixtures f ON f.id = fl.fixture_id
                WHERE fl.player_id = ?
                  AND fl.team_id = ?
                  AND f.starting_at < ?
                ORDER BY f.starting_at DESC
                LIMIT 10
                """,
                (player_id, team_id, fixture_date),
            ).fetchone()
            if minutes_row and minutes_row[2] and minutes_row[2] > 0:
                avg_min, starts, games = minutes_row
                if avg_min and avg_min > 0:
                    minutes_factor = min(avg_min / 90.0, 1.0)
                else:
                    # Fallback: ratio de titularidades
                    minutes_factor = (starts / games) if games else 0.5
                    # Si fue starter en >60% de partidos → titular habitual
                    if minutes_factor > 0.6:
                        minutes_factor = 0.85
                    else:
                        minutes_factor = 0.30
            else:
                minutes_factor = 0.5  # sin datos históricos

        # Position factor
        pos_str = pos_p or pos_s or ""
        pos_factor = _resolve_position_factor(pos_str)

        importance = sev_factor * minutes_factor * pos_factor

        # Parsear meta_json para nombre display
        display_name = full_name or common_name or "Unknown"
        try:
            meta = json.loads(meta_json) if meta_json else {}
            display_name = meta.get("athlete_display") or display_name
            if not pos_str:
                pos_str = meta.get("position", "")
                pos_factor = _resolve_position_factor(pos_str)
                importance = sev_factor * minutes_factor * pos_factor
        except (ValueError, TypeError):
            pass

        injuries.append({
            "name": display_name,
            "position": pos_str,
            "severity": severity or "Unknown",
            "severity_factor": round(sev_factor, 3),
            "minutes_factor": round(minutes_factor, 3),
            "position_factor": round(pos_factor, 3),
            "importance": round(importance, 3),
            "injury_type": injury_type or "Unknown",
            "injury_date": start_date,
        })

    injuries.sort(key=lambda x: x["importance"], reverse=True)

    total_impact = sum(i["importance"] for i in injuries)
    players_out = len(injuries)
    key_players_out = sum(1 for i in injuries if i["importance"] >= 0.4)
    avg_severity = sum(i["severity_factor"] for i in injuries) / players_out if players_out else 0.0

    return {
        "available": True,
        "total_impact": round(total_impact, 3),
        "players_out": players_out,
        "key_players_out": key_players_out,
        "avg_severity": round(avg_severity, 3),
        "top_injuries": injuries[:3],
        "no_data": False,
    }
