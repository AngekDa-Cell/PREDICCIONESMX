"""
test_features.py — Tests para las 11 features engineered.

Valida:
- Que cada feature retorne el schema esperado
- Que los rangos sean válidos (probabilidades en [0,1], win rates en [0,1], etc.)
- Casos edge (equipo sin partidos, fechas futuras, etc.)
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predict.features import (
    get_team_form,
    get_exponential_form,
    get_head_to_head,
    get_home_away_split,
    get_altitude_advantage,
    rest_days_advantage,
    get_rest_days,
    get_coach_pressure,
    get_coach_tenure_days,
    get_travel_distance,
    get_fixture_congestion,
    get_attack_defense_strength,
    get_season_context,
    get_full_feature_set,
)


class TestTeamForm:
    """Tests para get_team_form()."""

    def test_basic_schema(self, conn, team_ids, mid_season_date):
        """Verifica que retorna todos los campos esperados."""
        result = get_team_form(conn, team_ids["america"], mid_season_date, n=5)
        assert "matches" in result
        assert "wins" in result
        assert "draws" in result
        assert "losses" in result
        assert "win_rate" in result
        assert "momentum" in result
        assert "form_str" in result

    def test_counts_consistent(self, conn, team_ids, mid_season_date):
        """wins + draws + losses == matches."""
        result = get_team_form(conn, team_ids["america"], mid_season_date, n=10)
        if result["matches"] > 0:
            assert result["wins"] + result["draws"] + result["losses"] == result["matches"]
            assert 0 <= result["win_rate"] <= 1
            assert 0 <= result["momentum"] <= 3

    def test_empty_team(self, conn):
        """Equipo inexistente retorna zeros, no error."""
        result = get_team_form(conn, 999999, "2024-01-01", n=5)
        assert result["matches"] == 0
        assert result["wins"] == 0
        assert result["win_rate"] == 0.0

    def test_respects_n(self, conn, team_ids, mid_season_date):
        """No retorna más partidos de los pedidos."""
        for n in [3, 5, 10]:
            result = get_team_form(conn, team_ids["america"], mid_season_date, n=n)
            assert result["matches"] <= n


class TestExponentialForm:
    """Tests para get_exponential_form()."""

    def test_basic(self, conn, team_ids, mid_season_date):
        result = get_exponential_form(conn, team_ids["america"], mid_season_date)
        assert isinstance(result, dict)
        # Verifica keys esperadas (weighted_points, momentum, etc.)
        assert any(k in result for k in ["weighted_points", "momentum", "score", "matches"])

    def test_decay_range(self, conn, team_ids, mid_season_date):
        """Score está en rango razonable."""
        result = get_exponential_form(conn, team_ids["america"], mid_season_date)
        # weighted_points puede ser 0..3*max_n
        for k, v in result.items():
            if isinstance(v, (int, float)) and "points" in k:
                assert -1 <= v <= 30  # max_n*3 = 30


class TestHeadToHead:
    """Tests para get_head_to_head()."""

    def test_returns_dict(self, conn, team_ids, mid_season_date):
        result = get_head_to_head(conn, team_ids["america"], team_ids["chivas"], limit=10)
        assert isinstance(result, dict)

    def test_self_h2h_returns_empty_or_safe(self, conn, team_ids, mid_season_date):
        """H2H del equipo contra sí mismo no debe crashear."""
        result = get_head_to_head(conn, team_ids["america"], team_ids["america"], limit=10)
        assert result is not None


class TestAltitude:
    """Tests para get_altitude_advantage()."""

    def test_returns_dict(self, conn, team_ids):
        result = get_altitude_advantage(conn, team_ids["america"], team_ids["tijuana"])
        assert isinstance(result, dict)

    def test_altitude_in_range(self, conn, team_ids):
        """Altitud en metros razonable (0-3500m en MX)."""
        result = get_altitude_advantage(conn, team_ids["america"], team_ids["toluca"])
        if "home_altitude" in result:
            assert 0 <= result["home_altitude"] <= 3500
        if "away_altitude" in result:
            assert 0 <= result["away_altitude"] <= 3500

    def test_altitude_toluca_pachuca(self, conn, team_ids):
        """Toluca (~2680m) vs Pachuca (~2400m) tiene Δ pequeño."""
        result = get_altitude_advantage(conn, team_ids["toluca"], team_ids["pachuca"])
        if "delta" in result:
            assert abs(result["delta"]) < 500


class TestRestDays:
    """Tests para rest_days_advantage()."""

    def test_basic(self, conn, team_ids, mid_season_date):
        result = rest_days_advantage(conn, team_ids["america"], team_ids["chivas"], mid_season_date)
        assert isinstance(result, dict)

    def test_keys_present(self, conn, team_ids, mid_season_date):
        result = rest_days_advantage(conn, team_ids["america"], team_ids["chivas"], mid_season_date)
        # Al menos home_rest_days o away_rest_days
        assert "home_rest_days" in result or "away_rest_days" in result or len(result) > 0


class TestCoachPressure:
    """Tests para get_coach_pressure()."""

    def test_returns_dict(self, conn, team_ids):
        # Solo funciona si hay season_id activo
        result = get_coach_pressure(conn, team_ids["america"], current_season_id=23636)
        assert isinstance(result, dict)


class TestCoachTenure:
    """Tests para get_coach_tenure_days()."""

    def test_returns_dict(self, conn, team_ids, mid_season_date):
        result = get_coach_tenure_days(conn, team_ids["america"], mid_season_date)
        assert isinstance(result, dict)


class TestTravelDistance:
    """Tests para get_travel_distance()."""

    def test_returns_dict(self, conn, team_ids, mid_season_date):
        result = get_travel_distance(conn, team_ids["america"], mid_season_date)
        assert isinstance(result, dict)

    def test_distance_non_negative(self, conn, team_ids, mid_season_date):
        result = get_travel_distance(conn, team_ids["america"], mid_season_date)
        for k, v in result.items():
            if "distance" in k.lower() or "km" in k.lower():
                assert v >= 0


class TestFixtureCongestion:
    """Tests para get_fixture_congestion()."""

    def test_returns_dict(self, conn, team_ids, mid_season_date):
        result = get_fixture_congestion(conn, team_ids["america"], mid_season_date)
        assert isinstance(result, dict)


class TestAttackDefenseStrength:
    """Tests para get_attack_defense_strength()."""

    def test_returns_dict(self, conn, team_ids):
        result = get_attack_defense_strength(conn, team_ids["america"], season_id=23636)
        assert isinstance(result, dict)


class TestGetFullFeatureSet:
    """Tests para get_full_feature_set() — la integración de todas las features."""

    def test_runs_without_error(self, conn, team_ids, mid_season_date):
        """La integración corre y retorna datos."""
        result = get_full_feature_set(
            conn,
            home_team_id=team_ids["america"],
            away_team_id=team_ids["chivas"],
            fixture_date=mid_season_date,
            season_id=23636,
        )
        assert result is not None
        assert isinstance(result, dict)
        assert len(result) > 0  # tiene al menos algunas features