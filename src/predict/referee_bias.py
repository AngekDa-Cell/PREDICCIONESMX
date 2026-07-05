"""
referee_bias.py — Análisis de sesgo arbitral por árbitro.

Calcula, para cada árbitro con suficientes partidos:
- bias_score: desviación del home_win_rate vs 0.5 (linea base neutra)
  - positivo =倾向于local (más victorias locales)
  - negativo =倾向于visitante (más victorias visitantes)
- avg_total_goals, avg_home_goals, avg_away_goals
- games: partidos pitados (mínimo 30 para estadísticas confiables)

Uso en predicción:
- Si el árbitro tiene bias_score > +0.05 y juega local fuerte:
  → pequeño boost a probabilidad de victoria local (+2-3%)
- Si bias_score < -0.05 y juega local fuerte:
  → pequeño ajuste hacia visitante (-2-3%)

El paper "Home Advantage and Referee Bias in European Football" (Bryson et al.)
encuentra efectos pequeños pero consistentes. Aquí lo calibramos con datos MX.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Mínimo de partidos para considerar estadísticas confiables
MIN_GAMES_FOR_STATS: int = 30

# Sesgo máximo que aplicamos al ensemble (límite de seguridad)
MAX_BIAS_ABS: float = 0.15


@dataclass
class RefereeStats:
    """Estadísticas de sesgo de un árbitro."""
    referee_id: int
    name: str
    games: int
    home_win_rate: float
    draw_rate: float
    away_win_rate: float
    avg_total_goals: float | None = None
    avg_home_goals: float | None = None
    avg_away_goals: float | None = None
    bias_score: float = 0.0  # home_win_rate - 0.5

    @property
    def is_reliable(self) -> bool:
        """Stats confiables si tiene >= MIN_GAMES_FOR_STATS partidos."""
        return self.games >= MIN_GAMES_FOR_STATS

    @property
    def tendency(self) -> str:
        """Tendencia cualitativa."""
        if not self.is_reliable:
            return "unknown"
        if self.bias_score > 0.05:
            return "home-favored"
        if self.bias_score < -0.05:
            return "away-favored"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "referee_id": self.referee_id,
            "name": self.name,
            "games": self.games,
            "home_win_rate": self.home_win_rate,
            "draw_rate": self.draw_rate,
            "away_win_rate": self.away_win_rate,
            "avg_total_goals": self.avg_total_goals,
            "avg_home_goals": self.avg_home_goals,
            "avg_away_goals": self.avg_away_goals,
            "bias_score": self.bias_score,
            "tendency": self.tendency,
        }


class RefereeBiasAnalyzer:
    """Calcula y consulta estadísticas de sesgo arbitral."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._cache: dict[int, RefereeStats] = {}

    # ---------------------------------------------------------
    # Cálculo
    # ---------------------------------------------------------
    def compute_all(self, min_games: int = MIN_GAMES_FOR_STATS) -> list[RefereeStats]:
        """Calcula stats para todos los árbitros con >= min_games partidos."""
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT
                    ra.referee_id,
                    COALESCE(r.common_name, r.full_name) as name,
                    COUNT(DISTINCT f.id),
                    1.0 * SUM(CASE WHEN f.home_score > f.away_score THEN 1 ELSE 0 END) / COUNT(DISTINCT f.id) as hr,
                    1.0 * SUM(CASE WHEN f.home_score = f.away_score THEN 1 ELSE 0 END) / COUNT(DISTINCT f.id) as dr,
                    1.0 * SUM(CASE WHEN f.home_score < f.away_score THEN 1 ELSE 0 END) / COUNT(DISTINCT f.id) as ar,
                    AVG(f.home_score + f.away_score),
                    AVG(f.home_score),
                    AVG(f.away_score)
                FROM referee_assignments ra
                JOIN referees r ON r.id = ra.referee_id
                JOIN fixtures f ON f.id = ra.fixture_id
                WHERE ra.type_id = 6 AND f.home_score IS NOT NULL
                GROUP BY ra.referee_id
                HAVING COUNT(DISTINCT f.id) >= ?
                """,
                (min_games,),
            )
            results = []
            for row in c.fetchall():
                rid, name, games, hr, dr, ar, atg, ahg, aag = row
                stats = RefereeStats(
                    referee_id=rid,
                    name=name or f"Referee {rid}",
                    games=games,
                    home_win_rate=hr,
                    draw_rate=dr,
                    away_win_rate=ar,
                    avg_total_goals=atg,
                    avg_home_goals=ahg,
                    avg_away_goals=aag,
                    bias_score=hr - 0.5,
                )
                results.append(stats)
            return results
        finally:
            conn.close()

    def save_to_json(self, path: str | Path, min_games: int = MIN_GAMES_FOR_STATS) -> int:
        """Calcula y guarda a JSON. Retorna cantidad de árbitros."""
        results = self.compute_all(min_games=min_games)
        out = [r.to_dict() for r in results]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        return len(results)

    # ---------------------------------------------------------
    # Consultas (para usar en predicción)
    # ---------------------------------------------------------
    def get_stats(self, referee_id: int) -> RefereeStats | None:
        """Devuelve stats de un árbitro. Usa caché."""
        if referee_id in self._cache:
            return self._cache[referee_id]
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT
                    ra.referee_id,
                    COALESCE(r.common_name, r.full_name),
                    COUNT(DISTINCT f.id),
                    1.0 * SUM(CASE WHEN f.home_score > f.away_score THEN 1 ELSE 0 END) / COUNT(DISTINCT f.id),
                    1.0 * SUM(CASE WHEN f.home_score = f.away_score THEN 1 ELSE 0 END) / COUNT(DISTINCT f.id),
                    1.0 * SUM(CASE WHEN f.home_score < f.away_score THEN 1 ELSE 0 END) / COUNT(DISTINCT f.id),
                    AVG(f.home_score + f.away_score),
                    AVG(f.home_score),
                    AVG(f.away_score)
                FROM referee_assignments ra
                JOIN referees r ON r.id = ra.referee_id
                JOIN fixtures f ON f.id = ra.fixture_id
                WHERE ra.type_id = 6 AND f.home_score IS NOT NULL AND ra.referee_id = ?
                GROUP BY ra.referee_id
                """,
                (referee_id,),
            )
            row = c.fetchone()
            if row is None:
                return None
            rid, name, games, hr, dr, ar, atg, ahg, aag = row
            stats = RefereeStats(
                referee_id=rid,
                name=name or f"Referee {rid}",
                games=games,
                home_win_rate=hr,
                draw_rate=dr,
                away_win_rate=ar,
                avg_total_goals=atg,
                avg_home_goals=ahg,
                avg_away_goals=aag,
                bias_score=hr - 0.5,
            )
            self._cache[referee_id] = stats
            return stats
        finally:
            conn.close()

    def get_fixture_referee(self, fixture_id: int) -> int | None:
        """Devuelve el referee_id main del fixture, o None si no hay."""
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            c.execute(
                "SELECT referee_id FROM referee_assignments WHERE fixture_id = ? AND type_id = 6",
                (fixture_id,),
            )
            row = c.fetchone()
            return row[0] if row else None
        finally:
            conn.close()


# ---------------------------------------------------------
# Helper para predicción
# ---------------------------------------------------------
def adjust_prediction_for_referee(
    home_prob: float,
    draw_prob: float,
    away_prob: float,
    referee_stats: RefereeStats | None,
) -> tuple[float, float, float]:
    """Ajusta la predicción 1X2 según el sesgo del árbitro.

    Args:
        home_prob: probabilidad de victoria local (0-1)
        draw_prob: probabilidad de empate (0-1)
        away_prob: probabilidad de victoria visitante (0-1)
        referee_stats: stats del árbitro (None si no hay datos)

    Returns:
        Tuple (home', draw', away') ajustado.
    """
    if referee_stats is None or not referee_stats.is_reliable:
        return home_prob, draw_prob, away_prob

    # bias_score en [-MAX_BIAS_ABS, +MAX_BIAS_ABS]
    bias = max(-MAX_BIAS_ABS, min(MAX_BIAS_ABS, referee_stats.bias_score))

    # Calibración: 0.10 de bias absoluto = ~3pp en la predicción final
    # Mantenemos el ajuste pequeño porque el efecto de árbitro es modesto
    adjustment_pp = bias * 0.30  # máximo ±4.5pp

    home_new = home_prob + adjustment_pp / 100
    away_new = away_prob - adjustment_pp / 100
    draw_new = draw_prob  # el empate no se mueve

    # Normalizar para que sumen 1
    total = home_new + draw_new + away_new
    if total > 0:
        home_new /= total
        draw_new /= total
        away_new /= total

    return home_new, draw_new, away_new