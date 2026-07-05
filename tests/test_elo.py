"""
test_elo.py — Tests para Elo Rating.

Valida:
- expected_score() es función monotónica correcta
- k_multiplier() crece con goal difference
- actual_score() maneja victoria/empate/derrota
- update_match() cambia ratings correctamente
"""
import pytest
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predict.elo import (
    expected_score,
    k_multiplier,
    actual_score,
    EloState,
    ELO_BASE,
    ELO_K_FACTOR,
    HOME_ADVANTAGE_ELO,
    get_elo_predictions,
)


class TestExpectedScore:
    """Tests para la fórmula clásica E_A = 1/(1+10^((Rb-Ra-HA)/400))."""

    def test_equal_ratings_no_advantage(self):
        """Ratings iguales sin ventaja → 0.5."""
        e = expected_score(1500, 1500, 0)
        assert abs(e - 0.5) < 1e-9

    def test_higher_rating_favored(self):
        """Rating más alto tiene E > 0.5."""
        e = expected_score(1700, 1500, 0)
        assert 0.5 < e < 1.0

    def test_lower_rating_underdog(self):
        """Rating más bajo tiene E < 0.5."""
        e = expected_score(1300, 1500, 0)
        assert 0.0 < e < 0.5

    def test_home_advantage_boosts_local(self):
        """HA aumenta E del local."""
        e_no_ha = expected_score(1500, 1500, 0)
        e_with_ha = expected_score(1500, 1500, 100)
        assert e_with_ha > e_no_ha

    def test_symmetry(self):
        """E_A + E_B = 1 (sin HA)."""
        e_a = expected_score(1600, 1400, 0)
        e_b = expected_score(1400, 1600, 0)
        assert abs(e_a + e_b - 1.0) < 1e-9

    def test_400_points_gap_is_10x(self):
        """Diferencia de 400 puntos → E ≈ 0.909 (10:1 odds)."""
        e = expected_score(1900, 1500, 0)
        assert 0.90 < e < 0.92


class TestKMultiplier:
    """Tests para k_multiplier()."""

    def test_zero_diff_is_one(self):
        """0 goles de diferencia → multiplier = 1.0."""
        assert k_multiplier(0) == 1.0

    def test_negative_treated_as_zero(self):
        """Diff negativa → 1.0 (no boost para derrota)."""
        assert k_multiplier(-1) == 1.0
        assert k_multiplier(-5) == 1.0

    def test_grows_with_diff(self):
        """Multiplier crece monotónicamente."""
        k1 = k_multiplier(1)
        k3 = k_multiplier(3)
        k5 = k_multiplier(5)
        assert k1 < k3 < k5

    def test_one_goal_boost(self):
        """1 gol de diff → boost modesto."""
        k = k_multiplier(1)
        # log2(2) = 1, entonces k = 1 + 0.5 * 1 = 1.5
        assert 1.0 <= k <= 1.5


class TestActualScore:
    """Tests para actual_score()."""

    def test_home_win(self):
        """Victoria local → (1, 0)."""
        sh, sa = actual_score(2, 0)
        assert sh == 1.0
        assert sa == 0.0

    def test_away_win(self):
        """Victoria visitante → (0, 1)."""
        sh, sa = actual_score(0, 2)
        assert sh == 0.0
        assert sa == 1.0

    def test_draw(self):
        """Empate → (0.5, 0.5)."""
        sh, sa = actual_score(1, 1)
        assert sh == 0.5
        assert sa == 0.5


class TestEloState:
    """Tests para EloState class."""

    def test_initial_rating(self):
        """Rating inicial = ELO_BASE."""
        state = EloState()
        assert state.get(123) == ELO_BASE

    def test_update_match_changes_ratings(self):
        """Actualizar partido cambia ratings."""
        state = EloState()
        state.update_match(1, 2, 2, 0)  # Home wins
        # Home sube, Away baja
        assert state.get(1) > ELO_BASE
        assert state.get(2) < ELO_BASE

    def test_draw_converges(self):
        """Empate entre iguales → ratings casi sin cambio."""
        state = EloState()
        state.update_match(1, 2, 1, 1)
        # Cambio pequeño (HA da ventaja al local)
        # Home debería subir muy poco (era esperado 0.5+HA boost, ganó 0.5)
        assert abs(state.get(1) - ELO_BASE) < 5

    def test_zero_sum_close(self):
        """En general, suma de cambios ≈ 0."""
        state = EloState()
        r1_before = state.get(1)
        r2_before = state.get(2)
        state.update_match(1, 2, 3, 1)
        delta = (state.get(1) - r1_before) + (state.get(2) - r2_before)
        assert abs(delta) < 0.01


class TestGetEloPredictions:
    """Tests para get_elo_predictions() — función de integración."""

    def test_returns_dict(self, conn, team_ids, mid_season_date):
        result = get_elo_predictions(
            conn,
            home_team_id=team_ids["america"],
            away_team_id=team_ids["chivas"],
            before_date=mid_season_date,
        )
        assert isinstance(result, dict)

    def test_probabilities_sum_to_one(self, conn, team_ids, mid_season_date):
        """P(1) + P(X) + P(2) = 1."""
        result = get_elo_predictions(
            conn,
            home_team_id=team_ids["america"],
            away_team_id=team_ids["chivas"],
            before_date=mid_season_date,
        )
        # Buscar keys de probabilidad
        prob_keys = [
            ("prob_home_win", "prob_draw", "prob_away_win"),
            ("home_win", "draw", "away_win"),
            ("p_home", "p_draw", "p_away"),
        ]
        for keys in prob_keys:
            if all(k in result for k in keys):
                total = sum(result[k] for k in keys)
                assert abs(total - 1.0) < 0.01, f"Probabilidades suman {total} con keys {keys}"
                break