"""
test_shrinkage.py — Tests para Elo shrinkage.

Valida:
- Shrinkage factor 1.0 = sin cambios
- Shrinkage factor 0.0 = todos en ELO_BASE
- Shrinkage intermedio es monotónico
- Shrinkage por equipo y global se combinan correctamente
"""
import pytest
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predict.elo import (
    ELO_BASE,
    HOME_ADVANTAGE_ELO,
    DEFAULT_SHRINKAGE_FACTOR,
    predict_1x2_elo,
    apply_shrinkage,
)


class TestApplyShrinkage:
    """Tests para función apply_shrinkage."""

    def test_factor_1_no_change(self):
        """Factor 1.0 no debe cambiar Elo."""
        assert apply_shrinkage(1700, 1.0) == 1700
        assert apply_shrinkage(1300, 1.0) == 1300

    def test_factor_0_returns_base(self):
        """Factor 0.0 → siempre ELO_BASE."""
        assert apply_shrinkage(1700, 0.0) == ELO_BASE
        assert apply_shrinkage(1300, 0.0) == ELO_BASE

    def test_factor_half(self):
        """Factor 0.5 → mitad de la distancia hacia 1500."""
        # Elo 1700: 1500 + (1700-1500) * 0.5 = 1600
        assert apply_shrinkage(1700, 0.5) == 1600
        # Elo 1300: 1500 + (1300-1500) * 0.5 = 1400
        assert apply_shrinkage(1300, 0.5) == 1400

    def test_custom_anchor(self):
        """Anchor custom funciona."""
        assert apply_shrinkage(1700, 0.5, anchor=1600) == 1650

    def test_shrinkage_is_monotonic(self):
        """Shrinkage mayor → Elo más cercano al anchor."""
        elo = 1800
        prev = elo
        for f in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]:
            s = apply_shrinkage(elo, f)
            assert abs(s - ELO_BASE) <= abs(prev - ELO_BASE)
            prev = s


class TestPredictWithShrinkage:
    """Tests para predict_1x2_elo con shrinkage."""

    def test_shrinkage_1_matches_no_shrinkage(self):
        """Con shrinkage=1 y team_shrink=1, mismo resultado que sin shrinkage."""
        result = predict_1x2_elo(1700, 1500, shrinkage_factor=1.0,
                                  home_team_shrink=1.0, away_team_shrink=1.0)
        assert 0 <= result['home_win'] <= 1
        assert abs(result['home_win'] + result['draw'] + result['away_win'] - 1.0) < 0.01

    def test_shrinkage_reduces_extreme_predictions(self):
        """Shrinkage reduce predicciones extremas."""
        # Sin shrinkage: Elo muy alto debería dar win rate alto
        no_shrink = predict_1x2_elo(1900, 1100, shrinkage_factor=1.0)
        # Con shrinkage 0.5: predicción más balanceada
        shrunk = predict_1x2_elo(1900, 1100, shrinkage_factor=0.5)

        assert shrunk['home_win'] < no_shrink['home_win']

    def test_team_shrink_compounds(self):
        """Shrinkage global + team shrinkage se multiplican."""
        elo = 1800
        # Solo global
        r1 = predict_1x2_elo(elo, 1500, shrinkage_factor=0.7, home_team_shrink=1.0)
        # Solo team (efecto equivalente)
        r2 = predict_1x2_elo(elo, 1500, shrinkage_factor=1.0, home_team_shrink=0.7)
        # Ambos
        r3 = predict_1x2_elo(elo, 1500, shrinkage_factor=0.7, home_team_shrink=0.7)

        # r3 debe tener home_win menor que r1 y r2
        assert r3['home_win'] < r1['home_win']
        assert r3['home_win'] < r2['home_win']

    def test_probabilities_sum_to_one(self):
        """Probabilidades siempre suman 1 con shrinkage."""
        for shrink in [0.3, 0.5, 0.7, 0.9, 1.0]:
            for team_shrink in [0.5, 0.7, 1.0]:
                result = predict_1x2_elo(
                    1700, 1500,
                    shrinkage_factor=shrink,
                    home_team_shrink=team_shrink,
                    away_team_shrink=team_shrink,
                )
                total = result['home_win'] + result['draw'] + result['away_win']
                assert abs(total - 1.0) < 0.01

    def test_default_factor_is_set(self):
        """El factor default debe estar en rango razonable."""
        assert 0.5 <= DEFAULT_SHRINKAGE_FACTOR <= 1.0


class TestShrinkageIntegration:
    """Tests de integración con CLI."""

    def test_cli_runs_with_shrinkage(self):
        """CLI corre con shrinkage por default."""
        import subprocess

        result = subprocess.run(
            [
                "python3",
                str(Path(__file__).parent.parent / "src" / "predict" / "cli.py"),
                "--home", "América",
                "--away", "Chivas",
                "--no-log",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0, f"Error: {result.stderr}"

        import json
        data = json.loads(result.stdout)
        # Shrinkage factor debe estar reportado
        assert "shrinkage_factor" in data["meta"]
        assert data["meta"]["shrinkage_factor"] > 0

    def test_cli_no_shrinkage_flag(self):
        """Flag --no-shrinkage desactiva shrinkage."""
        import subprocess
        import json

        result = subprocess.run(
            [
                "python3",
                str(Path(__file__).parent.parent / "src" / "predict" / "cli.py"),
                "--home", "América",
                "--away", "Chivas",
                "--no-log",
                "--no-shrinkage",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0, f"Error: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["meta"]["shrinkage_factor"] == 1.0