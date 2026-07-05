"""
test_stacking.py — Tests para el stacking meta-learner.

Verifica:
1. cache_predictions devuelve estructura correcta
2. to_xy devuelve numpy arrays con shape correcto
3. XGBoost regularizado no overfittea en train
4. Brier score mejora consistentemente vs ensemble base (en al menos 1 split)
5. LogisticRegression funciona como fallback
"""
import sys
import json
import sqlite3
from pathlib import Path

import pytest
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from predict.stacking import (
    cache_predictions,
    to_xy,
    train_meta_learner,
    evaluate,
)


DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect(str(DB_PATH))
    yield c
    c.close()


@pytest.fixture(scope="module")
def cached_small(conn):
    """Cachea 100 partidos para tests rápidos."""
    return cache_predictions(conn, "2025-06-01", "2025-12-31")


def test_cache_predictions_returns_list(conn):
    """Debe devolver lista con keys correctas."""
    data = cache_predictions(conn, "2025-09-01", "2025-09-30")
    assert isinstance(data, list)
    if len(data) > 0:
        sample = data[0]
        assert 'fixture_id' in sample
        assert 'actual' in sample
        assert 'xg_home' in sample
        assert 'xg_draw' in sample
        assert 'xg_away' in sample
        assert 'elo_home' in sample
        assert 'dc_home' in sample
        assert 'heur_home' in sample
        assert 'attendance_ratio' in sample
        assert 'referee_bias' in sample


def test_to_xy_shapes(cached_small):
    """to_xy debe devolver numpy arrays."""
    X, y = to_xy(cached_small)
    assert isinstance(X, np.ndarray)
    assert isinstance(y, np.ndarray)
    if len(cached_small) > 0:
        assert X.shape[0] == y.shape[0]
        assert X.shape[1] == 17  # 12 probs + 5 features
        assert y.dtype == np.int32
        assert set(np.unique(y).tolist()).issubset({0, 1, 2})


def test_train_xgb_no_severe_overfit(cached_small):
    """XGBoost regularizado no debe sobre-ajustar masivamente."""
    if len(cached_small) < 50:
        pytest.skip("No hay suficientes datos para test")

    X, y = to_xy(cached_small)
    # Train/test split 70/30
    n = len(X)
    n_train = int(n * 0.7)
    X_train, X_test = X[:n_train], X[n_train:]
    y_train, y_test = y[:n_train], y[n_train:]

    if len(X_train) < 30 or len(X_test) < 10:
        pytest.skip("Split demasiado pequeño")

    model = train_meta_learner(X_train, y_train, model_type='xgb')
    train_probs = model.predict_proba(X_train)
    test_probs = model.predict_proba(X_test)

    train_acc = evaluate(train_probs, y_train)['accuracy']
    test_acc = evaluate(test_probs, y_test)['accuracy']

    # Train acc no debe ser >30pp mejor que test acc (overfitting severo)
    gap = train_acc - test_acc
    assert gap < 30, f"Overfitting: train_acc={train_acc:.1f}, test_acc={test_acc:.1f}, gap={gap:.1f}pp"


def test_lr_fallback_works(cached_small):
    """Logistic Regression debe entrenar sin errores."""
    if len(cached_small) < 50:
        pytest.skip("No hay suficientes datos")

    X, y = to_xy(cached_small)
    model = train_meta_learner(X, y, model_type='lr')
    probs = model.predict_proba(X)
    assert probs.shape == (len(X), 3)
    # Cada fila suma a 1 (probabilidades válidas)
    sums = probs.sum(axis=1)
    np.testing.assert_allclose(sums, 1.0, atol=1e-6)


def test_baseline_better_than_random_2025():
    """El ensemble base 2025 debe estar sobre el azar (33.3%) por amplio margen."""
    # Lee resultados cacheados de un experimento real
    result_path = PROJECT_ROOT / "data" / "stacking_xgb_2yr.json"
    if not result_path.exists():
        pytest.skip("No hay resultados de backtest para validar")

    data = json.load(open(result_path))
    base_acc = data['baseline']['accuracy']
    assert base_acc > 45, f"Baseline accuracy {base_acc} muy bajo"


def test_brier_improvement_consistent():
    """El Brier del stacking debe mejorar vs baseline en al menos 1 experimento."""
    # Revisar todos los experimentos guardados
    results = []
    for fname in ['stacking_xgb.json', 'stacking_xgb_2yr.json', 'stacking_xgb_h2.json',
                  'stacking_xgb_reg.json']:
        path = PROJECT_ROOT / "data" / fname
        if path.exists():
            d = json.load(open(path))
            results.append((fname, d.get('delta_brier', 0)))

    if not results:
        pytest.skip("No hay resultados de backtest")

    # Al menos 2 experimentos deben mejorar Brier
    improvements = sum(1 for _, b in results if b < -0.005)
    assert improvements >= 2, f"Brier no mejora consistentemente: {results}"