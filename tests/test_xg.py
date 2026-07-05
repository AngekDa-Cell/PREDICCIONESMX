"""
test_xg.py — Tests para el sistema xG (Expected Goals proxy).

Cubre:
- Entrenamiento del modelo xG
- Predicción individual
- Predicción 1X2
- Precompute cache
- Integración con backtest
"""
import pytest
import sys
import json
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.xg import (
    get_connection, extract_shot_stats, build_feature_matrix,
    predict_xg_for_record, load_xg_model, train_xg_model,
    precompute_xg_lookup, get_xg_1x2_prediction,
    _poisson_1x2, _ridge_regression,
)


class TestXGTraining:
    def test_ridge_regression_basic(self):
        """Ridge regression en datos simples debe recuperar coeficientes."""
        # Datos lineales: y = 2*x0 + 3*x1
        X = np.array([[1, 0], [0, 1], [1, 1], [2, 3]], dtype=float)
        y = np.array([2, 3, 5, 13], dtype=float)  # 2*1 + 3*0=2, 2*0+3*1=3, ...
        intercept, coefs = _ridge_regression(X, y, alpha=0.01)
        # Intercept ≈ 0, coefs ≈ [2, 3]
        assert abs(intercept) < 0.1
        assert abs(coefs[0] - 2.0) < 0.2
        assert abs(coefs[1] - 3.0) < 0.2

    def test_train_xg_model_produces_coefs(self, db):
        """Entrenar xG debe producir coeficientes en escala log."""
        # No guardamos el modelo para no afectar el de producción
        model = train_xg_model(db, save=False)
        assert model['method'] == 'log_ridge'
        assert 'intercept' in model
        assert 'coefs' in model
        assert len(model['coefs']) == 6  # 6 features
        # Coef de shot_quality debe ser positivo (más calidad → más goles)
        shot_quality_idx = model['feature_order'].index('shot_quality')
        assert model['coefs'][shot_quality_idx] > 0
        # Coef de sot debe ser positivo
        sot_idx = model['feature_order'].index('shots-on-target')
        assert model['coefs'][sot_idx] > 0

    def test_train_in_sample_correlation(self, db):
        """El xG proxy debe correlacionar con goles reales (in-sample)."""
        model = train_xg_model(db, save=False)
        records = extract_shot_stats(db)
        preds = [predict_xg_for_record(r, model) for r in records]
        actuals = [r.goals for r in records]
        corr = np.corrcoef(preds, actuals)[0, 1]
        # Correlación moderada-alta esperada
        assert corr > 0.45, f"Correlación xG-goles demasiado baja: {corr:.3f}"

    def test_xg_monotonic_by_sot(self, db):
        """A más shots-on-target, xG debe crecer monotónicamente."""
        model = train_xg_model(db, save=False)
        records = extract_shot_stats(db)
        sot_buckets = {}
        for r in records:
            sot_buckets.setdefault(r.sot, []).append(predict_xg_for_record(r, model))
        means = {k: np.mean(v) for k, v in sot_buckets.items() if len(v) >= 30}
        sorted_keys = sorted(means.keys())
        for i in range(len(sorted_keys) - 1):
            k1, k2 = sorted_keys[i], sorted_keys[i + 1]
            assert means[k1] <= means[k2] + 0.05, \
                f"No monotónico: sot={k1} xG={means[k1]:.3f} > sot={k2} xG={means[k2]:.3f}"


class TestPoisson1X2:
    def test_poisson_sum_to_one(self):
        """P(1X2) debe sumar ~1."""
        p_h, p_d, p_a = _poisson_1x2(1.5, 1.2, max_goals=10)
        s = p_h + p_d + p_a
        assert abs(s - 1.0) < 0.01, f"Suma no es 1: {s}"

    def test_poisson_stronger_home(self):
        """λ_home mayor debe dar P(home) > P(away)."""
        p_h, p_d, p_a = _poisson_1x2(2.0, 1.0, max_goals=10)
        assert p_h > p_a

    def test_poisson_equal_lambdas(self):
        """λ iguales → P(home) = P(away)."""
        p_h, _, p_a = _poisson_1x2(1.5, 1.5, max_goals=10)
        assert abs(p_h - p_a) < 0.01

    def test_poisson_low_lambdas_favors_draw(self):
        """λ_home ≈ λ_away ≈ 0.5 → empate es probable."""
        p_h, p_d, p_a = _poisson_1x2(0.5, 0.5, max_goals=8)
        # En 0.5 vs 0.5, P(draw) > P(home o away)
        assert p_d > p_h
        assert p_d > p_a


class TestXGPrediction:
    def test_get_xg_1x2_returns_valid_probs(self, db):
        """get_xg_1x2_prediction debe retornar probs que suman 1."""
        # Buscar dos equipos con datos suficientes
        cur = db.cursor()
        home = cur.execute("SELECT id FROM teams WHERE name LIKE '%Am%rica%' LIMIT 1").fetchone()
        away = cur.execute("SELECT id FROM teams WHERE name LIKE '%Cruz Azul%' LIMIT 1").fetchone()
        if not home or not away:
            pytest.skip("Equipos no encontrados")
        pred = get_xg_1x2_prediction(db, home['id'], away['id'], before_date='2025-06-01')
        assert 'home_win' in pred
        assert 'draw' in pred
        assert 'away_win' in pred
        s = pred['home_win'] + pred['draw'] + pred['away_win']
        assert abs(s - 1.0) < 0.01, f"Probs no suman 1: {s}"
        # Lambdas razonables
        assert 0.3 <= pred['lambda_home'] <= 4.5
        assert 0.3 <= pred['lambda_away'] <= 4.5

    def test_get_xg_uses_cache_when_provided(self, db):
        """get_xg con cache debe dar resultados similares que sin cache."""
        home = 2687
        away = 2626
        before = '2025-06-01'
        # Sin cache
        pred_slow = get_xg_1x2_prediction(db, home, away, before_date=before)
        # Con cache
        cache = precompute_xg_lookup(db)
        pred_fast = get_xg_1x2_prediction(db, home, away, before_date=before, _cache=cache)
        # Probs deben ser aproximadamente iguales (diferencias por detalles de filtrado)
        for k in ['home_win', 'draw', 'away_win']:
            assert abs(pred_slow[k] - pred_fast[k]) < 0.10, f"Mismatch en {k}: {pred_slow[k]:.4f} vs {pred_fast[k]:.4f}"


class TestXGLookup:
    def test_precompute_cache_covers_all_teams(self, db):
        """Cache debe incluir todos los equipos con datos de shots."""
        records = extract_shot_stats(db)
        teams_with_data = set(r.team_id for r in records)
        cache = precompute_xg_lookup(db)
        for tid in teams_with_data:
            assert tid in cache['attack'], f"Team {tid} no está en cache.attack"
            assert tid in cache['conceded'], f"Team {tid} no está en cache.conceded"

    def test_precompute_cache_dates_sorted(self, db):
        """Las fechas en cache deben estar ordenadas."""
        cache = precompute_xg_lookup(db)
        dates = cache['dates']
        assert dates == sorted(dates)

    def test_rolling_xg_returns_baseline_for_no_history(self, db):
        """Para equipo sin historial, xG debe ser el baseline (1.0)."""
        # Buscar fechas muy tempranas donde el equipo no tenía datos
        # Usamos team_id 999999 que no existe
        cache = precompute_xg_lookup(db)
        # Para un equipo que SÍ está pero con fecha anterior a su primer partido
        home = 2687  # América
        before = '2010-01-01'  # Antes de cualquier partido
        pred = get_xg_1x2_prediction(db, home, home, before_date=before, _cache=cache)
        # attack debe ser ~1.0 (baseline fallback)
        assert abs(pred['home_attack_xg'] - 1.0) < 0.01


class TestXGModelPersistence:
    def test_model_file_exists(self):
        """El modelo debe estar persistido en data/xg_model.json."""
        path = PROJECT_ROOT / "data" / "xg_model.json"
        assert path.exists(), f"Modelo no encontrado en {path}"

    def test_model_file_loads(self):
        """El modelo guardado debe poder cargarse."""
        path = PROJECT_ROOT / "data" / "xg_model.json"
        m = load_xg_model(path)
        assert m['method'] == 'log_ridge'
        assert len(m['coefs']) == 6
        assert m['n_train'] > 1000
