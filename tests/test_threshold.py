"""
test_threshold.py — Tests para threshold mínimo de confianza.

Valida que el flag --min-confidence funciona correctamente
y que las predicciones con confianza baja se marcan como tales.
"""
import pytest
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CLI_PATH = PROJECT_ROOT / "src" / "predict" / "cli.py"


class TestThresholdFlag:
    """Tests del flag --min-confidence."""

    def test_low_threshold_no_warning(self):
        """Threshold muy bajo (10%) no debe disparar warning."""
        result = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                "--home", "América",
                "--away", "Chivas",
                "--min-confidence", "0.10",
                "--no-log",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "Confianza BAJA" not in result.stdout

    def test_high_threshold_warning_shown(self):
        """Threshold muy alto (95%) debe disparar warning."""
        result = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                "--home", "América",
                "--away", "Chivas",
                "--min-confidence", "0.95",
                "--no-log",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "Confianza BAJA" in result.stdout
        assert "Modelo no apuesta" in result.stdout


class TestRecalibrationFlag:
    """Tests del flag --recalibrated."""

    def test_recalibrated_runs(self):
        """--recalibrated corre sin error."""
        result = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                "--home", "América",
                "--away", "Chivas",
                "--recalibrated",
                "--no-log",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "RECALIBRADAS" in result.stdout

    def test_without_recalibration_no_label(self):
        """Sin --recalibrated, no aparece el label."""
        result = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                "--home", "América",
                "--away", "Chivas",
                "--no-log",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "RECALIBRADAS" not in result.stdout