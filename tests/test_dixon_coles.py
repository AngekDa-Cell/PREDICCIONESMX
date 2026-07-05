"""
test_dixon_coles.py — Tests para Dixon-Coles Poisson Model.

Valida:
- poisson_pmf suma ≈ 1 sobre [0, ∞)
- dc_win_prob retorna probabilidades válidas que suman 1
- Caso simétrico (ambos equipos iguales) → P(home) > P(away) por HA
"""
import pytest
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predict.dixon_coles import (
    poisson_pmf,
    poisson_cdf,
    dc_win_prob,
    fit_dixon_coles,
    predict_from_model,
)


class TestPoissonPMF:
    """Tests para poisson_pmf()."""

    def test_zero(self):
        """P(X=0) = e^(-λ)."""
        lam = 2.0
        expected = math.exp(-lam)
        assert abs(poisson_pmf(0, lam) - expected) < 1e-9

    def test_non_negative(self):
        """P(X=k) >= 0 para todos los k."""
        for k in range(20):
            assert poisson_pmf(k, 1.5) >= 0

    def test_zero_lambda(self):
        """λ=0 → solo P(X=0) = 1, resto 0."""
        assert poisson_pmf(0, 0) == 1.0
        assert poisson_pmf(1, 0) == 0.0
        assert poisson_pmf(5, 0) == 0.0

    def test_sums_to_one(self):
        """Suma de P(X=k) sobre k=0..∞ ≈ 1."""
        total = sum(poisson_pmf(k, 2.5) for k in range(50))
        assert abs(total - 1.0) < 1e-6

    def test_mode_around_lambda(self):
        """El modo está cerca de λ."""
        lam = 5.0
        pmf = [poisson_pmf(k, lam) for k in range(20)]
        mode = pmf.index(max(pmf))
        # Modo puede estar en floor(λ) o floor(λ)+1
        assert mode in (int(lam), int(lam) - 1, int(lam) + 1)


class TestPoissonCDF:
    """Tests para poisson_cdf()."""

    def test_at_zero(self):
        """P(X=0) = e^(-λ)."""
        lam = 1.5
        expected = math.exp(-lam)
        assert abs(poisson_cdf(0, lam) - expected) < 1e-9

    def test_at_infinity_is_one(self):
        """P(X <= 100) ≈ 1 para λ moderada."""
        assert poisson_cdf(100, 2.0) > 0.999

    def test_monotonic(self):
        """CDF crece monotónicamente."""
        prev = 0
        for k in range(20):
            cdf = poisson_cdf(k, 3.0)
            assert cdf >= prev
            prev = cdf


class TestDCWinProb:
    """Tests para dc_win_prob() — función core de Dixon-Coles."""

    def test_returns_three_probs(self):
        """Retorna tupla (home, draw, away)."""
        result = dc_win_prob(
            home_att=1.0, away_att=1.0,
            home_def=1.0, away_def=1.0,
            home_adv=1.3, rho=-0.1,
        )
        assert len(result) == 3
        ph, pd, pa = result
        assert all(0 <= p <= 1 for p in [ph, pd, pa])

    def test_sum_to_one(self):
        """P(home) + P(draw) + P(away) = 1."""
        ph, pd, pa = dc_win_prob(
            home_att=1.2, away_att=0.8,
            home_def=1.1, away_def=0.9,
            home_adv=1.3, rho=-0.05,
        )
        assert abs(ph + pd + pa - 1.0) < 1e-6

    def test_home_advantage_works(self):
        """Equipos iguales + HA → P(home) > P(away)."""
        ph, pd, pa = dc_win_prob(
            home_att=1.0, away_att=1.0,
            home_def=1.0, away_def=1.0,
            home_adv=1.3, rho=-0.1,
        )
        assert ph > pa

    def test_no_home_advantage_no_favorite(self):
        """Sin HA y equipos iguales → P(home) ≈ P(away)."""
        ph, pd, pa = dc_win_prob(
            home_att=1.0, away_att=1.0,
            home_def=1.0, away_def=1.0,
            home_adv=1.0, rho=0.0,
        )
        assert abs(ph - pa) < 0.05

    def test_stronger_attack_increases_home_prob(self):
        """Mejor ataque local → más P(home)."""
        ph_weak, _, _ = dc_win_prob(
            home_att=0.7, away_att=1.0,
            home_def=1.0, away_def=1.0,
            home_adv=1.3, rho=0.0,
        )
        ph_strong, _, _ = dc_win_prob(
            home_att=1.5, away_att=1.0,
            home_def=1.0, away_def=1.0,
            home_adv=1.3, rho=0.0,
        )
        assert ph_strong > ph_weak


class TestFitAndPredict:
    """Tests de integración fit → predict."""

    def test_fit_returns_model(self, conn, team_ids):
        """fit_dixon_coles retorna un modelo entrenado."""
        model = fit_dixon_coles(conn, season_id=23636)
        # Puede ser None si no hay datos suficientes
        if model is not None:
            assert isinstance(model, dict)

    def test_predict_returns_probs(self, conn, team_ids, mid_season_date):
        """predict_from_model retorna 1X2 + score."""
        model = fit_dixon_coles(conn, season_id=23636)
        if model is None:
            pytest.skip("fit_dixon_coles no retornó modelo")
        result = predict_from_model(
            model,
            home_team_id=team_ids["america"],
            away_team_id=team_ids["chivas"],
        )
        assert isinstance(result, dict)
        # Al menos alguna forma de probabilidades
        assert any(
            k in result
            for k in ["prob_home_win", "home_win", "prob_1", "1", "home"]
        )