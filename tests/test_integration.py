"""
test_integration.py — Tests de integración end-to-end.

Verifica que el flujo completo (predict CLI) corre y produce output válido.
"""
import pytest
import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CLI_PATH = PROJECT_ROOT / "src" / "predict" / "cli.py"


class TestCLI:
    """Tests del CLI principal."""

    def test_validate_runs(self):
        """`--validate` corre sin error."""
        result = subprocess.run(
            [sys.executable, str(CLI_PATH), "--validate"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "Partidos" in result.stdout or "fixtures" in result.stdout.lower()

    def test_predict_runs(self):
        """Predicción simple corre sin error."""
        result = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                "--home", "América",
                "--away", "Chivas",
                "--no-log",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        # Output debe tener probabilidades
        assert '"probabilities"' in result.stdout or '"prob"' in result.stdout
        assert '"home"' in result.stdout or '"1"' in result.stdout

    def test_predict_probabilities_valid(self):
        """Probabilidades suman ~1 y están en [0,1]."""
        import json

        result = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                "--home", "América",
                "--away", "Chivas",
                "--no-log",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        probs = data.get("probabilities", {})
        if "1" in probs and "X" in probs and "2" in probs:
            p1 = probs["1"]["prob"]
            px = probs["X"]["prob"]
            p2 = probs["2"]["prob"]
            total = p1 + px + p2
            assert abs(total - 1.0) < 0.01
            assert 0 <= p1 <= 1
            assert 0 <= px <= 1
            assert 0 <= p2 <= 1

    def test_h2h_runs(self):
        """Modo H2H corre sin error."""
        result = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                "--h2h",
                "--home", "América",
                "--away", "Chivas",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0

    def test_invalid_team_fails_gracefully(self):
        """Equipo inexistente falla con error claro, no crashea."""
        result = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                "--home", "Equipo Inventado XYZ",
                "--away", "Otro Inventado ABC",
                "--no-log",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        # El CLI termina con returncode 0 pero muestra mensaje de error
        # Lo importante es que NO crashea con stacktrace
        assert "❌" in result.stdout or "Error" in result.stdout or "no encontrado" in result.stdout.lower()
        assert "Traceback" not in result.stderr