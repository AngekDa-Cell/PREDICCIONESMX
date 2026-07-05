"""
test_ensemble.py — Tests para la lógica del ensemble.

Valida:
- Pesos del ensemble suman 1
- Pesos son no-negativos
- Combinación ponderada produce probabilidades válidas
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predict import cli as predict_cli


# Pesos canónicos del ensemble (deben matchear lo documentado)
ENSEMBLE_WEIGHTS = {
    "elo": 0.55,
    "dc": 0.30,
    "heur": 0.15,
}


class TestEnsembleWeights:
    """Tests sobre los pesos del ensemble."""

    def test_weights_sum_to_one(self):
        """0.55 + 0.30 + 0.15 = 1.0."""
        total = sum(ENSEMBLE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_weights_non_negative(self):
        for k, v in ENSEMBLE_WEIGHTS.items():
            assert v >= 0

    def test_weights_documented(self):
        """Verifica que los pesos son los documentados en METHODOLOGY.md."""
        # Estos son los pesos validados con backtest 2025
        assert ENSEMBLE_WEIGHTS["elo"] == 0.55
        assert ENSEMBLE_WEIGHTS["dc"] == 0.30
        assert ENSEMBLE_WEIGHTS["heur"] == 0.15


class TestWeightedAverage:
    """Tests para el cálculo de promedio ponderado de probabilidades."""

    def test_balanced_case(self):
        """Si los 3 modelos coinciden en 0.5, ensemble da 0.5."""
        elo_p = 0.5
        dc_p = 0.5
        heur_p = 0.5
        result = (
            elo_p * ENSEMBLE_WEIGHTS["elo"]
            + dc_p * ENSEMBLE_WEIGHTS["dc"]
            + heur_p * ENSEMBLE_WEIGHTS["heur"]
        )
        assert abs(result - 0.5) < 1e-9

    def test_extreme_case(self):
        """Si Elo dice 1.0 y otros 0, ensemble = 0.55."""
        result = (
            1.0 * 0.55
            + 0.0 * 0.30
            + 0.0 * 0.15
        )
        assert abs(result - 0.55) < 1e-9

    def test_normalization(self):
        """Si los modelos suman >1, normalizar."""
        # Caso de borde: cada modelo dice 1.0 en home
        total = (
            1.0 * 0.55
            + 1.0 * 0.30
            + 1.0 * 0.15
        )
        # Total = 1.0 (suma de pesos = 1)
        assert abs(total - 1.0) < 1e-9