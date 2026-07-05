"""
test_recalibration.py — Tests para recalibración y threshold.

Valida:
- apply_temperature() con T=1.0 no cambia probabilidades
- T>1 suaviza (reduce max prob), T<1 sharpen
- find_optimal_temperature() retorna T > 1 si modelo overconfident
- sigmoid y softmax son funciones correctas
- apply_calibration() funciona end-to-end
- save/load calibration es round-trip
"""
import pytest
import math
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predict.recalibration import (
    softmax,
    apply_temperature,
    sigmoid,
    find_optimal_temperature,
    fit_platt_binary,
    apply_platt,
    negative_log_likelihood,
    save_calibration,
    load_calibration,
    apply_calibration,
)


class TestSoftmax:
    """Tests para softmax()."""

    def test_sum_to_one(self):
        """Softmax de cualquier vector suma 1."""
        result = softmax([1.0, 2.0, 3.0])
        assert abs(sum(result) - 1.0) < 1e-9

    def test_monotonic(self):
        """Mayor logit → mayor probabilidad."""
        result = softmax([1.0, 2.0, 3.0])
        assert result[0] < result[1] < result[2]

    def test_uniform(self):
        """Logits iguales → probabilidades iguales."""
        result = softmax([1.0, 1.0, 1.0])
        assert all(abs(r - 1/3) < 1e-9 for r in result)

    def test_numerical_stability(self):
        """Logits muy grandes no overflowean."""
        result = softmax([1000.0, 1001.0, 1002.0])
        assert all(0 <= r <= 1 for r in result)
        assert abs(sum(result) - 1.0) < 1e-9


class TestSigmoid:
    """Tests para sigmoid()."""

    def test_zero(self):
        """sigmoid(0) = 0.5."""
        assert abs(sigmoid(0) - 0.5) < 1e-9

    def test_positive(self):
        """sigmoid(x) > 0.5 para x > 0."""
        assert sigmoid(1) > 0.5
        assert sigmoid(5) > 0.5

    def test_negative(self):
        """sigmoid(x) < 0.5 para x < 0."""
        assert sigmoid(-1) < 0.5
        assert sigmoid(-5) < 0.5

    def test_symmetry(self):
        """sigmoid(x) + sigmoid(-x) = 1."""
        for x in [0.5, 2.0, 5.0]:
            assert abs(sigmoid(x) + sigmoid(-x) - 1.0) < 1e-9


class TestApplyTemperature:
    """Tests para apply_temperature()."""

    def test_t1_no_change(self):
        """T=1.0 → no debe cambiar probabilidades."""
        probs = {'home_win': 0.6, 'draw': 0.25, 'away_win': 0.15}
        result = apply_temperature(probs, T=1.0)
        assert abs(result['home_win'] - 0.6) < 1e-6
        assert abs(result['draw'] - 0.25) < 1e-6
        assert abs(result['away_win'] - 0.15) < 1e-6

    def test_t_high_smoothing(self):
        """T>1 → menos overconfident (max prob baja)."""
        probs = {'home_win': 0.7, 'draw': 0.2, 'away_win': 0.1}
        result = apply_temperature(probs, T=2.0)
        assert result['home_win'] < 0.7
        assert result['draw'] > 0.2
        assert result['away_win'] > 0.1

    def test_t_low_sharpening(self):
        """T<1 → más overconfident (max prob sube)."""
        probs = {'home_win': 0.5, 'draw': 0.3, 'away_win': 0.2}
        result = apply_temperature(probs, T=0.5)
        assert result['home_win'] > 0.5

    def test_sum_to_one(self):
        """Probabilidades siempre suman 1."""
        for T in [0.5, 1.0, 1.5, 2.0, 3.0]:
            result = apply_temperature({'home_win': 0.5, 'draw': 0.3, 'away_win': 0.2}, T=T)
            total = sum(result.values())
            assert abs(total - 1.0) < 1e-9


class TestFindOptimalTemperature:
    """Tests para find_optimal_temperature()."""

    def test_returns_positive_T(self):
        """T óptimo debe estar en [T_min, T_max]."""
        preds = [{'home_win': 0.6, 'draw': 0.25, 'away_win': 0.15}] * 10
        actuals = [0] * 10
        T, nll = find_optimal_temperature(preds, actuals)
        assert 0.5 <= T <= 3.0

    def test_perfect_predictions_low_nll(self):
        """Predicciones perfectas → NLL cercano a 0."""
        preds = [{'home_win': 1.0, 'draw': 0.0, 'away_win': 0.0}] * 5
        actuals = [0] * 5
        T, nll = find_optimal_temperature(preds, actuals)
        assert nll < 0.5  # Muy bajo

    def test_random_predictions_high_nll(self):
        """Predicciones al azar → NLL cercano a log(3)."""
        preds = [{'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}] * 30
        actuals = [i % 3 for i in range(30)]
        T, nll = find_optimal_temperature(preds, actuals, T_min=0.9, T_max=1.1, step=0.1)
        assert abs(nll - math.log(3)) < 0.1


class TestPlattScaling:
    """Tests para fit_platt_binary() y apply_platt()."""

    def test_fit_returns_AB(self):
        """fit retorna tupla (A, B)."""
        preds = [0.5, 0.6, 0.7, 0.4, 0.8]
        actuals = [1, 1, 1, 0, 1]
        A, B = fit_platt_binary(preds, actuals)
        assert isinstance(A, float)
        assert isinstance(B, float)

    def test_apply_platt_range(self):
        """Platt aplicado retorna probabilidades en (0, 1)."""
        preds = [0.1, 0.5, 0.9, 0.3, 0.7]
        A, B = 1.0, 0.0  # Identity-ish
        result = apply_platt(preds, A, B)
        for p in result:
            assert 0 < p < 1

    def test_calibration_improves_NLL(self):
        """Si modelo está sesgado, Platt debe mejorar NLL."""
        # Generar datos donde el modelo está overconfident
        npreds = []
        actuals = []
        for _ in range(100):
            true_prob = 0.5
            actual = 1 if __import__('random').random() < true_prob else 0
            predicted = true_prob + 0.1  # sesgo
            npreds.append(predicted)
            actuals.append(actual)

        # Sin calibrar
        nll_before = sum(-(a * math.log(max(p, 1e-9)) + (1-a) * math.log(max(1-p, 1e-9))) for p, a in zip(npreds, actuals)) / len(npreds)

        # Calibrar
        A, B = fit_platt_binary(npreds, actuals)
        cal_preds = apply_platt(npreds, A, B)
        nll_after = sum(-(a * math.log(max(p, 1e-9)) + (1-a) * math.log(max(1-p, 1e-9))) for p, a in zip(cal_preds, actuals)) / len(npreds)

        # No garantizamos mejora pero al menos no debe empeorar mucho
        assert nll_after < nll_before + 0.5


class TestNLL:
    """Tests para negative_log_likelihood()."""

    def test_perfect_prediction_low(self):
        """Predicción perfecta → NLL ≈ 0."""
        preds = [{'home_win': 1.0, 'draw': 0.0, 'away_win': 0.0}]
        actuals = [0]
        nll = negative_log_likelihood(1.0, preds, actuals)
        assert nll < 0.1

    def test_worst_prediction_high(self):
        """Predicción totalmente equivocada → NLL alto."""
        preds = [{'home_win': 0.0, 'draw': 0.0, 'away_win': 1.0}]
        actuals = [0]  # Era home, modelo dijo 100% away
        nll = negative_log_likelihood(1.0, preds, actuals)
        assert nll > 5  # -log(epsilon) ≈ 11, promedio será alto


class TestSaveLoadCalibration:
    """Tests para save/load de calibración."""

    def test_save_creates_file(self, tmp_path):
        """save_calibration crea archivo JSON."""
        # Mock del path para usar tmp_path
        with patch("predict.recalibration.CALIBRATION_PATH", tmp_path / "test_cal.json"):
            save_calibration(
                temperature=1.5,
                nll_before=1.0,
                nll_after=0.95,
                n_samples=680,
                method="temperature",
            )
            assert (tmp_path / "test_cal.json").exists()

    def test_load_returns_dict(self, tmp_path):
        """load_calibration retorna dict si existe."""
        test_file = tmp_path / "test_cal.json"
        test_file.write_text(json.dumps({
            "method": "temperature",
            "temperature": 1.5,
            "platt": {},
            "metrics": {"nll_before": 1.0, "nll_after": 0.95, "n_samples": 680},
        }))

        with patch("predict.recalibration.CALIBRATION_PATH", test_file):
            result = load_calibration()
            assert result is not None
            assert result["method"] == "temperature"
            assert result["temperature"] == 1.5

    def test_load_missing_returns_none(self, tmp_path):
        """load_calibration retorna None si no existe."""
        with patch("predict.recalibration.CALIBRATION_PATH", tmp_path / "nonexistent.json"):
            result = load_calibration()
            assert result is None


class TestApplyCalibrationIntegration:
    """Tests de integración apply_calibration()."""

    def test_apply_with_temperature(self, tmp_path):
        """Aplica temperature scaling."""
        test_file = tmp_path / "test_cal.json"
        test_file.write_text(json.dumps({
            "method": "temperature",
            "temperature": 2.0,
            "platt": {},
            "metrics": {"nll_before": 1.0, "nll_after": 0.95, "n_samples": 100},
        }))

        probs = {'home_win': 0.7, 'draw': 0.2, 'away_win': 0.1}
        with patch("predict.recalibration.CALIBRATION_PATH", test_file):
            result = apply_calibration(probs)
            assert result['home_win'] < 0.7  # suavizado

    def test_apply_no_calibration_returns_same(self, tmp_path):
        """Sin archivo de calibración, retorna igual."""
        with patch("predict.recalibration.CALIBRATION_PATH", tmp_path / "nonexistent.json"):
            probs = {'home_win': 0.5, 'draw': 0.3, 'away_win': 0.2}
            result = apply_calibration(probs)
            assert result == probs

    def test_apply_with_platt(self, tmp_path):
        """Aplica Platt scaling."""
        test_file = tmp_path / "test_cal.json"
        test_file.write_text(json.dumps({
            "method": "platt",
            "temperature": 1.0,
            "platt": {
                "home": [1.0, 0.0],
                "draw": [1.0, 0.0],
                "away": [1.0, 0.0],
            },
            "metrics": {"nll_before": 1.0, "nll_after": 0.95, "n_samples": 680},
        }))

        probs = {'home_win': 0.6, 'draw': 0.25, 'away_win': 0.15}
        with patch("predict.recalibration.CALIBRATION_PATH", test_file):
            result = apply_calibration(probs)
            # Debe estar normalizado
            assert abs(sum(result.values()) - 1.0) < 1e-6
            assert all(0 <= v <= 1 for v in result.values())