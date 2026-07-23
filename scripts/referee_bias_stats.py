#!/usr/bin/env python3
"""
referee_bias_stats.py — Calcula estadísticas de bias por referee.

Para cada referee con suficientes partidos (>=10), calcula:
- cards_per_game (avg de yellow + red cards en partidos que arbitró)
- fouls_per_game (avg fouls en partidos que arbitró)
- penalty_rate (penaltis pitados / partidos)
- home_win_bias (cuánto favoreció a equipos locales vs visitante)

Output: data/referee_bias_stats.json → usado por features.py como referee_factor
"""

import sys
import json
import sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


MIN_GAMES = 10  # Mínimo de partidos para incluir referee


def calculate_referee_stats(conn, min_games=MIN_GAMES):
    """Calcula estadísticas por referee (cards, fouls, pens, home bias)."""

    # Total partidos por referee
    counts = conn.execute("""
        SELECT ra.referee_id, r.full_name, COUNT(*) AS games
        FROM referee_assignments ra
        JOIN referees r ON r.id = ra.referee_id
        JOIN fixtures f ON f.id = ra.fixture_id
        WHERE f.home_score IS NOT NULL AND f.away_score IS NOT NULL
          AND f.league_id = 743
        GROUP BY ra.referee_id
        HAVING COUNT(*) >= ?
    """, (min_games,)).fetchall()

    referee_stats = {}

    for ref_id, ref_name, games in counts:
        # Cards por partido (yellow + red)
        cards = conn.execute("""
            SELECT AVG(fs.stat_value)
            FROM fixture_statistics fs
            JOIN referee_assignments ra ON ra.fixture_id = fs.fixture_id
            WHERE ra.referee_id = ?
              AND fs.stat_type IN ('yellowcards', 'redcards')
            GROUP BY fs.fixture_id
        """, (ref_id,)).fetchall()

        cards_avg = sum(c[0] or 0 for c in cards) / len(cards) if cards else 0

        # Fouls por partido
        fouls = conn.execute("""
            SELECT AVG(fs.stat_value)
            FROM fixture_statistics fs
            JOIN referee_assignments ra ON ra.fixture_id = fs.fixture_id
            WHERE ra.referee_id = ?
              AND fs.stat_type = 'fouls'
            GROUP BY fs.fixture_id
        """, (ref_id,)).fetchone()
        fouls_avg = fouls[0] or 0 if fouls else 0

        # Penaltis por partido
        pens = conn.execute("""
            SELECT AVG(fs.stat_value)
            FROM fixture_statistics fs
            JOIN referee_assignments ra ON ra.fixture_id = fs.fixture_id
            WHERE ra.referee_id = ?
              AND fs.stat_type = 'penalties'
            GROUP BY fs.fixture_id
        """, (ref_id,)).fetchone()
        pens_avg = pens[0] or 0 if pens else 0

        # Home win rate (vs league baseline 47%)
        wins = conn.execute("""
            SELECT
              SUM(CASE WHEN f.home_score > f.away_score THEN 1 ELSE 0 END) as home_wins,
              SUM(CASE WHEN f.away_score > f.home_score THEN 1 ELSE 0 END) as away_wins,
              SUM(CASE WHEN f.home_score = f.away_score THEN 1 ELSE 0 END) as draws
            FROM referee_assignments ra
            JOIN fixtures f ON f.id = ra.fixture_id
            WHERE ra.referee_id = ?
              AND f.home_score IS NOT NULL AND f.away_score IS NOT NULL
              AND f.league_id = 743
        """, (ref_id,)).fetchone()

        home_wins = wins[0] or 0
        away_wins = wins[1] or 0
        draws = wins[2] or 0
        total_decided = home_wins + away_wins

        if total_decided > 0:
            home_win_rate = home_wins / (home_wins + away_wins)
            # Baseline Liga MX: ~46% home win (cuando no hay empate)
            home_bias = home_win_rate - 0.46
        else:
            home_bias = 0

        referee_stats[str(ref_id)] = {
            "name": ref_name,
            "games": games,
            "cards_per_game": round(cards_avg, 2),
            "fouls_per_game": round(fouls_avg, 2),
            "penalties_per_game": round(pens_avg, 3),
            "home_win_rate": round(home_wins / (home_wins + away_wins), 3) if total_decided else 0,
            "home_bias": round(home_bias, 3),  # Positivo = favorece locales
            "card_strictness": "strict" if cards_avg > 5.0 else ("lenient" if cards_avg < 3.0 else "normal"),
        }

    return referee_stats


def compute_referee_factor(referee_stats: dict, min_games: int = MIN_GAMES) -> dict:
    """Genera un factor de referee normalizado para usar en ensemble.

    El factor combina:
    - stricness (más cards = más interrupción, favorece ligeramente a visitante)
    - home_bias (si el árbitro favorece locales o visitantes)
    - foul_rate (más fouls = más tiempo perdido = menos goles)
    """
    # Normalizar cada métrica a -0.5..+0.5
    if not referee_stats:
        return {}

    factor = {}
    for ref_id, stats in referee_stats.items():
        cards_factor = (stats["cards_per_game"] - 4.0) / 10.0  # 0 = baseline 4 cards
        home_bias = stats["home_bias"] * 5.0  # -1..+1 aprox
        foul_factor = (stats["fouls_per_game"] - 25.0) / 30.0  # baseline 25 fouls

        # Factor compuesto: -1 a +1
        # Positivo = árbitro que favorece ligeramente al LOCAL
        composite = (
            home_bias * 0.6           # 60% peso al home bias histórico
            + cards_factor * 0.2      # 20% stricness
            + foul_factor * 0.2       # 20% fouls
        )
        composite = max(-1.0, min(1.0, composite))

        factor[ref_id] = {
            "name": stats["name"],
            "games": stats["games"],
            "factor": round(composite, 3),  # -1..+1
            "home_win_rate": stats["home_win_rate"],
            "card_strictness": stats["card_strictness"],
        }

    return factor


def main():
    db_path = PROJECT_ROOT / "data" / "predictions_mx.db"
    out_path = PROJECT_ROOT / "data" / "referee_bias_stats.json"

    print(f"📊 Calculando stats de referee bias ({MIN_GAMES}+ juegos)...")
    conn = sqlite3.connect(str(db_path))
    try:
        referee_stats = calculate_referee_stats(conn)
        referee_factor = compute_referee_factor(referee_stats)

        # Guardar
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_games_threshold": MIN_GAMES,
            "referee_count": len(referee_stats),
            "stats": referee_stats,
            "factors": referee_factor,
        }
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"✅ Stats para {len(referee_stats)} referees → {out_path}")

        # Top 5 más estrictos / más permisivos
        sorted_by_bias = sorted(referee_factor.values(), key=lambda x: x["factor"])
        print(f"\n Top 5 favorecen VISITANTE (-factor):")
        for r in sorted_by_bias[:5]:
            print(f"   {r['name']:30s} factor={r['factor']:+.3f} ({r['card_strictness']})")

        print(f"\n Top 5 favorecen LOCAL (+factor):")
        for r in sorted_by_bias[-5:]:
            print(f"   {r['name']:30s} factor={r['factor']:+.3f} ({r['card_strictness']})")

    finally:
        conn.close()


if __name__ == "__main__":
    main()