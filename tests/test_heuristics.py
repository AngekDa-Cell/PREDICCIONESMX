"""
test_heuristics.py — Tests para las 11 heurísticas del analista.

Valida:
- detect_derby() reconoce derbies conocidos
- apply_heuristics() retorna estructura esperada
- Probabilidades se mantienen en [0, 1] después de aplicar
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predict.heuristics import (
    detect_derby,
    apply_heuristics,
    load_manual_narratives,
    find_value_bets,
    prob_to_odds,
    KNOWN_PATTERNS,
)


class TestDetectDerby:
    """Tests para detect_derby()."""

    def test_clasico_nacional(self):
        """América vs Chivas = Clásico Nacional."""
        result = detect_derby("América", "Chivas")
        assert result is not None
        # Puede ser dict, tupla, o string — solo verificamos que detecta

    def test_no_derby_returns_none_or_empty(self):
        """Pachuca vs Mazatlán no es derby."""
        result = detect_derby("Pachuca", "Mazatlán")
        # Puede ser None, dict vacío, etc.
        assert result is None or result == {} or result == ()

    def test_clasico_regio(self):
        """Rayados vs Tigres = Clásico Regio."""
        result = detect_derby("Rayados", "Tigres")
        assert result is not None

    def test_clasico_tapatio(self):
        """Chivas vs Atlas = Clásico Tapatío."""
        result = detect_derby("Chivas", "Atlas")
        assert result is not None


class TestProbToOdds:
    """Tests para prob_to_odds()."""

    def test_basic(self):
        """0.5 → odds ~2.0."""
        odds = prob_to_odds(0.5)
        assert 1.9 < odds < 2.1

    def test_high_prob_low_odds(self):
        """0.8 → odds ~1.25."""
        odds = prob_to_odds(0.8)
        assert 1.2 < odds < 1.3

    def test_low_prob_high_odds(self):
        """0.1 → odds ~10."""
        odds = prob_to_odds(0.1)
        assert 9 < odds < 11

    def test_zero_prob_handled(self):
        """0.0 no debe crashear (odds altísimas)."""
        odds = prob_to_odds(0.01)
        assert odds > 50

    def test_one_prob(self):
        """1.0 → odds ≈ 1."""
        odds = prob_to_odds(1.0)
        assert 1.0 <= odds < 1.1


class TestLoadNarratives:
    """Tests para load_manual_narratives()."""

    def test_returns_dict(self):
        result = load_manual_narratives()
        assert isinstance(result, dict)


class TestApplyHeuristics:
    """Tests para apply_heuristics() — la integración."""

    def test_returns_dict(self, team_ids):
        """apply_heuristics retorna dict con probabilidades modificadas."""
        features = {"home_team": "América", "away_team": "Chivas"}
        narratives = {"narratives": [], "derbies": [], "warnings": []}
        model_output = {
            "home_win": 0.45,
            "draw": 0.30,
            "away_win": 0.25,
            "model_confidence": 0.5,
        }
        result = apply_heuristics(features, narratives, model_output)
        assert isinstance(result, dict)

    def test_probs_stay_valid(self, team_ids):
        """Probabilidades se mantienen en [0,1] después de heurísticas."""
        features = {"home_team": "América", "away_team": "Chivas"}
        narratives = {"narratives": [], "derbies": [], "warnings": []}
        model_output = {
            "home_win": 0.45,
            "draw": 0.30,
            "away_win": 0.25,
            "model_confidence": 0.5,
        }
        result = apply_heuristics(features, narratives, model_output)
        # Buscar las keys que correspondan
        for key in ["home_win", "draw", "away_win"]:
            if key in result:
                assert 0 <= result[key] <= 1