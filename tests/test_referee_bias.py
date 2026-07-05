"""
test_referee_bias.py — Tests para la heurística de referee bias (Fase 9).

Cubre:
- RefereeBiasAnalyzer (computación de stats)
- get_referee_bias feature
- apply_heuristics con referee_bias
- Validación con datos reales del ingester
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# Setup path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.predict.referee_bias import (
    MIN_GAMES_FOR_STATS,
    MAX_BIAS_ABS,
    RefereeStats,
    RefereeBiasAnalyzer,
    adjust_prediction_for_referee,
)
from src.predict.features import get_referee_bias


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "predictions_mx.db"


@pytest.fixture(scope="module")
def conn():
    """Conexión a la BD compartida por todos los tests."""
    assert DB_PATH.exists(), f"BD no encontrada: {DB_PATH}"
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture(scope="module")
def analyzer():
    return RefereeBiasAnalyzer(str(DB_PATH))


# ─────────────────────────────────────────────────────────────────────────────
# RefereeStats
# ─────────────────────────────────────────────────────────────────────────────

class TestRefereeStats:
    """Tests sobre la dataclass RefereeStats."""

    def test_tendency_home_favored(self):
        s = RefereeStats(
            referee_id=1, name="Test", games=50,
            home_win_rate=0.60, draw_rate=0.20, away_win_rate=0.20,
            bias_score=0.10,
        )
        assert s.tendency == "home-favored"

    def test_tendency_away_favored(self):
        s = RefereeStats(
            referee_id=2, name="Test", games=50,
            home_win_rate=0.40, draw_rate=0.25, away_win_rate=0.35,
            bias_score=-0.10,
        )
        assert s.tendency == "away-favored"

    def test_tendency_neutral(self):
        s = RefereeStats(
            referee_id=3, name="Test", games=50,
            home_win_rate=0.48, draw_rate=0.25, away_win_rate=0.27,
            bias_score=-0.02,
        )
        assert s.tendency == "neutral"

    def test_tendency_unknown_when_unreliable(self):
        s = RefereeStats(
            referee_id=4, name="Test", games=10,
            home_win_rate=0.70, draw_rate=0.20, away_win_rate=0.10,
            bias_score=0.20,
        )
        assert s.tendency == "unknown"

    def test_is_reliable(self):
        reliable = RefereeStats(
            referee_id=5, name="Test", games=MIN_GAMES_FOR_STATS,
            home_win_rate=0.50, draw_rate=0.25, away_win_rate=0.25,
            bias_score=0.0,
        )
        assert reliable.is_reliable is True

    def test_not_reliable(self):
        unreliable = RefereeStats(
            referee_id=6, name="Test", games=MIN_GAMES_FOR_STATS - 1,
            home_win_rate=0.50, draw_rate=0.25, away_win_rate=0.25,
            bias_score=0.0,
        )
        assert unreliable.is_reliable is False


# ─────────────────────────────────────────────────────────────────────────────
# RefereeBiasAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class TestRefereeBiasAnalyzer:
    """Tests sobre el analizador."""

    def test_compute_all_returns_list(self, analyzer):
        results = analyzer.compute_all(min_games=30)
        assert isinstance(results, list)
        assert len(results) > 0, "Debería haber árbitros con >=30 partidos"

    def test_all_results_reliable(self, analyzer):
        """Todos los referees devueltos deben tener >=30 partidos."""
        results = analyzer.compute_all(min_games=30)
        for r in results:
            assert r.games >= 30, f"{r.name} tiene solo {r.games} partidos"
            assert r.is_reliable is True

    def test_results_consistency(self, analyzer):
        """bias_score = home_win_rate - 0.5."""
        results = analyzer.compute_all(min_games=30)
        for r in results:
            expected = r.home_win_rate - 0.5
            assert abs(r.bias_score - expected) < 1e-6, (
                f"{r.name}: bias_score={r.bias_score} != HR-0.5={expected}"
            )

    def test_rates_sum_to_one(self, analyzer):
        results = analyzer.compute_all(min_games=30)
        for r in results:
            total = r.home_win_rate + r.draw_rate + r.away_win_rate
            assert abs(total - 1.0) < 0.01, (
                f"{r.name}: rates sum={total} (debe ser ~1.0)"
            )

    def test_save_to_json(self, analyzer, tmp_path):
        out = tmp_path / "test_ref_stats.json"
        n = analyzer.save_to_json(out, min_games=30)
        assert n > 0
        assert out.exists()
        import json
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert len(data) == n

    def test_get_stats_caches(self, analyzer):
        """Verifica que el caché funcione."""
        # Primera llamada (consulta BD)
        rid = 3679  # Oscar Mejia
        s1 = analyzer.get_stats(rid)
        # Segunda llamada (debería venir de caché)
        s2 = analyzer.get_stats(rid)
        assert s1 is s2  # Mismo objeto por caché


# ─────────────────────────────────────────────────────────────────────────────
# adjust_prediction_for_referee
# ─────────────────────────────────────────────────────────────────────────────

class TestAdjustPrediction:
    """Tests del ajuste de probabilidades."""

    def test_no_referee_keeps_prediction(self):
        hp, dp, ap = adjust_prediction_for_referee(0.5, 0.3, 0.2, None)
        assert hp == 0.5
        assert dp == 0.3
        assert ap == 0.2

    def test_unreliable_referee_keeps_prediction(self):
        s = RefereeStats(
            referee_id=1, name="Test", games=10,
            home_win_rate=0.7, draw_rate=0.2, away_win_rate=0.1,
            bias_score=0.2,
        )
        hp, dp, ap = adjust_prediction_for_referee(0.5, 0.3, 0.2, s)
        assert hp == 0.5
        assert dp == 0.3
        assert ap == 0.2

    def test_home_favored_boosts_home(self):
        """Árbitro倾向于local debe aumentar home_prob."""
        s = RefereeStats(
            referee_id=1, name="HomeRef", games=50,
            home_win_rate=0.55, draw_rate=0.25, away_win_rate=0.20,
            bias_score=0.05,
        )
        hp, dp, ap = adjust_prediction_for_referee(0.5, 0.3, 0.2, s)
        assert hp > 0.5, f"home_prob debería crecer: {hp}"
        assert ap < 0.2, f"away_prob debería decrecer: {ap}"
        # Suma sigue siendo ~1
        assert abs(hp + dp + ap - 1.0) < 0.01

    def test_away_favored_boosts_away(self):
        """Árbitro倾向于visitante debe aumentar away_prob."""
        s = RefereeStats(
            referee_id=2, name="AwayRef", games=50,
            home_win_rate=0.40, draw_rate=0.25, away_win_rate=0.35,
            bias_score=-0.10,
        )
        hp, dp, ap = adjust_prediction_for_referee(0.5, 0.3, 0.2, s)
        assert hp < 0.5, f"home_prob debería decrecer: {hp}"
        assert ap > 0.2, f"away_prob debería crecer: {ap}"
        assert abs(hp + dp + ap - 1.0) < 0.01

    def test_draw_unchanged(self):
        """Empate no se mueve por el ajuste de árbitro."""
        s = RefereeStats(
            referee_id=3, name="Test", games=50,
            home_win_rate=0.60, draw_rate=0.20, away_win_rate=0.20,
            bias_score=0.10,
        )
        _, dp, _ = adjust_prediction_for_referee(0.5, 0.3, 0.2, s)
        assert abs(dp - 0.3) < 0.001

    def test_extreme_bias_capped(self):
        """Bias extremo no debe generar ajustes enormes."""
        s = RefereeStats(
            referee_id=4, name="ExtremeRef", games=100,
            home_win_rate=0.80, draw_rate=0.10, away_win_rate=0.10,
            bias_score=0.30,
        )
        hp, dp, ap = adjust_prediction_for_referee(0.5, 0.3, 0.2, s)
        # bias_score cappeado a MAX_BIAS_ABS (0.15)
        # ajuste = 0.15 * 0.30 = 0.045 = 4.5pp
        # home: 0.5 + 0.045 = 0.545
        # Cap efectivo: el ajuste máximo es ±4.5pp
        assert hp <= 0.55, f"home_prob no debería pasar de 0.55: {hp}"
        assert ap >= 0.18, f"away_prob no debería bajar de 0.18: {ap}"


# ─────────────────────────────────────────────────────────────────────────────
# get_referee_bias feature
# ─────────────────────────────────────────────────────────────────────────────

class TestGetRefereeBiasFeature:
    """Tests del feature get_referee_bias()."""

    def test_unknown_fixture_returns_neutral(self, conn):
        result = get_referee_bias(conn, fixture_id=999999999)
        assert result["available"] is False
        assert result["games"] == 0
        assert result["bias_score"] == 0.0

    def test_unknown_referee_returns_neutral(self, conn):
        result = get_referee_bias(conn, referee_id=999999999)
        assert result["available"] is False

    def test_known_referee_returns_stats(self, conn):
        """A. Escobedo González (id=15644) tiene 115+ partidos, bias conocido."""
        result = get_referee_bias(conn, referee_id=15644)
        assert result["available"] is True
        assert result["referee_id"] == 15644
        assert result["games"] > 50
        # Tiene bias倾向于visitante según muestra anterior
        assert result["is_reliable"] is True

    def test_feature_handles_no_fixture_no_referee(self, conn):
        """Sin fixture_id ni referee_id → neutral."""
        result = get_referee_bias(conn)
        assert result["available"] is False

    def test_fixture_with_referee(self, conn):
        """Fixture que SÍ tiene árbitro asignado."""
        # Buscar un fixture con referee asignado
        c = conn.cursor()
        c.execute(
            "SELECT fixture_id FROM referee_assignments WHERE type_id = 6 LIMIT 1"
        )
        row = c.fetchone()
        assert row is not None, "BD no tiene assignments"
        fid = row[0]
        result = get_referee_bias(conn, fixture_id=fid)
        assert result["referee_id"] is not None
        assert "name" in result
        assert "games" in result


# ─────────────────────────────────────────────────────────────────────────────
# Sanity check: distribución de bias en datos reales
# ─────────────────────────────────────────────────────────────────────────────

class TestBiasDistribution:
    """Verifica que la distribución de bias es razonable."""

    def test_mean_bias_near_zero(self, analyzer):
        """El bias medio de la liga debería estar cerca de 0."""
        results = analyzer.compute_all(min_games=30)
        biases = [r.bias_score for r in results]
        mean = sum(biases) / len(biases)
        # En Liga MX la literatura reporta leve倾向于visitante (~-0.03)
        # Permitimos un rango más amplio
        assert -0.10 < mean < 0.10, f"Media de bias sospechosa: {mean:.3f}"

    def test_stdev_reasonable(self, analyzer):
        """Stdev del bias no debería ser ni muy pequeño ni muy grande."""
        results = analyzer.compute_all(min_games=30)
        biases = [r.bias_score for r in results]
        n = len(biases)
        mean = sum(biases) / n
        var = sum((b - mean) ** 2 for b in biases) / n
        stdev = var ** 0.5
        # Con datos reales hemos visto stdev ~0.07
        assert 0.02 < stdev < 0.15, f"Stdev sospechosa: {stdev:.3f}"

    def test_min_games_threshold(self, analyzer):
        """Todos los árbitros en resultados deben cumplir min_games."""
        results = analyzer.compute_all(min_games=50)
        for r in results:
            assert r.games >= 50


# ─────────────────────────────────────────────────────────────────────────────
# Integración: heurística + feature
# ─────────────────────────────────────────────────────────────────────────────

class TestHeuristicsIntegration:
    """Verifica que la heurística de referee_bias se aplica correctamente."""

    def test_apply_heuristics_with_referee(self):
        """apply_heuristics debe procesar features['referee_bias']."""
        from src.predict.heuristics import apply_heuristics

        features = {
            "referee_bias": {
                "available": True,
                "is_reliable": True,
                "referee_id": 1,
                "name": "TestRef",
                "games": 50,
                "bias_score": -0.10,  #倾向于visitante
                "tendency": "away-favored",
                "home_win_rate": 0.40,
                "draw_rate": 0.25,
                "away_win_rate": 0.35,
            },
            "mx_coefficients": {},
        }
        model = {"home_win": 0.5, "draw": 0.3, "away_win": 0.2, "model_confidence": 0.6}

        out = apply_heuristics(features, {}, model)
        # Debe haber al menos un adjustment de tipo referee
        types = [a["type"] for a in out["heuristic_adjustments"]]
        assert "referee_away_bias" in types, f"types: {types}"
        # away_win debe crecer vs model.away_win
        assert out["away_win"] > model["away_win"], (
            f"away_win no creció: {out['away_win']} vs {model['away_win']}"
        )

    def test_apply_heuristics_unreliable_referee(self):
        """Sin stats confiables, no se debe aplicar heurística."""
        from src.predict.heuristics import apply_heuristics

        features = {
            "referee_bias": {
                "available": True,
                "is_reliable": False,
                "referee_id": 1,
                "name": "NewRef",
                "games": 10,
                "bias_score": 0.20,
                "tendency": "unknown",
            },
            "mx_coefficients": {},
        }
        model = {"home_win": 0.5, "draw": 0.3, "away_win": 0.2, "model_confidence": 0.6}

        out = apply_heuristics(features, {}, model)
        types = [a["type"] for a in out["heuristic_adjustments"]]
        assert "referee_home_bias" not in types
        assert "referee_away_bias" not in types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])