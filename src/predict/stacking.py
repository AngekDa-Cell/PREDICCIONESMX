"""
stacking.py — Stacking meta-learner sobre predicciones del ensemble base.

Combina las salidas de los 4 modelos (xG, Elo, DC, heur) + features clave
usando XGBoost o Logistic Regression como meta-learner.

Features del meta-learner:
- xg_home, xg_draw, xg_away
- elo_home, elo_draw, elo_away
- dc_home, dc_draw, dc_away
- heuristic_home, heuristic_draw, heuristic_away
- attendance_ratio (cuando disponible)
- weather_available flag
- referee_bias_score
- altitude_diff
- is_derby

Target: 0=home, 1=draw, 2=away

Validación:
- Train: 2023-2024 (680 partidos disponibles con attendance)
- Test: 2025 (340 partidos)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"

# Ensure we can import predict.* from anywhere
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np


def cache_predictions(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> List[Dict]:
    """Cachea las predicciones de los 4 modelos base + features clave.

    Args:
        conn: conexión sqlite
        start_date, end_date: rango de fechas

    Returns:
        Lista de dicts con keys:
          fixture_id, actual (0/1/2),
          xg (home/draw/away), elo (...), dc (...), heuristic (...),
          attendance_ratio (0-1 o None),
          weather_available (bool),
          referee_bias_score (float),
          altitude_diff (int),
          is_derby (bool)
    """
    from predict.features import get_full_feature_set
    from predict.dixon_coles import fit_dixon_coles, predict_from_model
    from predict.elo import get_elo_predictions
    from predict.xg import get_xg_1x2_prediction, precompute_xg_lookup
    from predict.heuristics import apply_heuristics, load_manual_narratives
    from predict.misc_utils import get_shrinkage_factor

    # Precompute xG lookup
    xg_lookup = precompute_xg_lookup(conn)

    fixtures = conn.execute("""
        SELECT id, home_team_id, away_team_id, season_id, starting_at
        FROM fixtures
        WHERE league_id=743
          AND starting_at BETWEEN ? AND ?
          AND home_score IS NOT NULL
        ORDER BY starting_at
    """, (start_date, end_date)).fetchall()
    print(f"Cacheando predicciones para {len(fixtures)} partidos...")

    seasons_to_fit = set(f[3] for f in fixtures)
    dc_models = {sid: fit_dixon_coles(conn, sid) for sid in seasons_to_fit}
    dc_models = {k: v for k, v in dc_models.items() if v is not None}

    narratives = load_manual_narratives()

    team_shrink_path = PROJECT_ROOT / "data" / "team_local_shrinkage.json"
    team_shrinkages = {}
    if team_shrink_path.exists():
        with open(team_shrink_path) as f:
            team_shrinkages = json.load(f).get("teams", {})

    shrinkage = get_shrinkage_factor()

    cached = []
    n_done = 0
    for fid, h, a, sid, fdate in fixtures:
        if sid not in dc_models:
            continue
        try:
            features = get_full_feature_set(conn, h, a, sid, fdate)
            features['home_team_name'] = conn.execute("SELECT name FROM teams WHERE id=?", (h,)).fetchone()[0]
            features['away_team_name'] = conn.execute("SELECT name FROM teams WHERE id=?", (a,)).fetchone()[0]

            home_alt = features['altitude'].get('home_altitude', 0) or 0
            away_alt = features['altitude'].get('away_altitude', 0) or 0
            rest_diff = features['rest'].get('rest_diff', 0)
            form_diff = features['home_form'].get('momentum', 0) - features['away_form'].get('momentum', 0)
            h2h_rate = features['h2h'].get('a_win_rate', 0.5)

            dc_o = predict_from_model(dc_models[sid], h, a, home_alt, away_alt, rest_diff, form_diff, h2h_rate)
            elo_o = get_elo_predictions(conn, h, a, before_date=fdate, shrinkage_factor=shrinkage, team_shrinkages=team_shrinkages)
            adj_o = apply_heuristics(features, narratives, dc_o)
            xg_o = get_xg_1x2_prediction(conn, h, a, before_date=fdate, _cache=xg_lookup)

            row = conn.execute("SELECT home_score, away_score FROM fixtures WHERE id=?", (fid,)).fetchone()
            actual = 0 if row[0] > row[1] else (1 if row[0] == row[1] else 2)

            # Features clave para meta-learner
            att = features.get('attendance_ratio', {})
            att_ratio = att.get('ratio') if att.get('available') else None

            weather = features.get('weather', {})
            weather_avail = 1 if weather.get('available') else 0

            ref = features.get('referee_bias', {})
            ref_bias = ref.get('bias_score', 0.0) if ref.get('is_reliable') else 0.0

            altitude_diff = features['altitude'].get('altitude_diff', 0) or 0
            is_derby = 1 if adj_o.get('is_derby', False) else 0

            cached.append({
                'fixture_id': fid,
                'starting_at': fdate,
                'actual': actual,
                'xg_home': xg_o['home_win'],
                'xg_draw': xg_o['draw'],
                'xg_away': xg_o['away_win'],
                'elo_home': elo_o['home_win'],
                'elo_draw': elo_o['draw'],
                'elo_away': elo_o['away_win'],
                'dc_home': dc_o['home_win'],
                'dc_draw': dc_o['draw'],
                'dc_away': dc_o['away_win'],
                'heur_home': adj_o['home_win'],
                'heur_draw': adj_o['draw'],
                'heur_away': adj_o['away_win'],
                'attendance_ratio': att_ratio,
                'weather_avail': weather_avail,
                'referee_bias': ref_bias,
                'altitude_diff': altitude_diff,
                'is_derby': is_derby,
            })
        except Exception as ex:
            import traceback
            print(f"  Error en fixture {fid}: {ex}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            if len(cached) == 0 and n_done <= 3:
                # Print first few errors para debug
                pass

        n_done += 1
        if n_done % 100 == 0:
            print(f"  {n_done}/{len(fixtures)} done...")

    print(f"✅ Cacheadas {len(cached)} predicciones")
    return cached


def to_xy(cached: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
    """Convierte lista de dicts en X (features) e y (target).

    Features usadas:
      12 probs de modelos + 5 features clave
    """
    feature_keys = [
        'xg_home', 'xg_draw', 'xg_away',
        'elo_home', 'elo_draw', 'elo_away',
        'dc_home', 'dc_draw', 'dc_away',
        'heur_home', 'heur_draw', 'heur_away',
        'attendance_ratio',
        'weather_avail',
        'referee_bias',
        'altitude_diff',
        'is_derby',
    ]

    X = []
    y = []
    for r in cached:
        row = []
        for k in feature_keys:
            v = r.get(k)
            if v is None:
                # Attendance ratio missing → use median (neutral)
                v = 0.55
            row.append(float(v))
        X.append(row)
        y.append(r['actual'])

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


def train_meta_learner(
    X_train: np.ndarray,
    y_train: np.ndarray,
    model_type: str = 'xgb',
) -> object:
    """Entrena el meta-learner (XGBoost o Logistic Regression)."""
    if model_type == 'xgb':
        from xgboost import XGBClassifier
        model = XGBClassifier(
            n_estimators=30,           # menos árboles (overfit)
            max_depth=2,               # menos profundidad
            learning_rate=0.05,        # learning rate más bajo
            reg_alpha=1.0,             # regularización L1
            reg_lambda=2.0,            # regularización L2
            min_child_weight=10,       # require más muestras por hoja
            objective='multi:softprob',
            num_class=3,
            random_state=42,
            n_jobs=1,
            verbosity=0,
        )
    elif model_type == 'lr':
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression(
            max_iter=2000,
            C=0.5,                    # regularización
            random_state=42,
        )
    elif model_type == 'xgb_tiny':
        from xgboost import XGBClassifier
        model = XGBClassifier(
            n_estimators=10,
            max_depth=1,
            learning_rate=0.1,
            objective='multi:softprob',
            num_class=3,
            random_state=42,
            n_jobs=1,
            verbosity=0,
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    model.fit(X_train, y_train)
    return model


def predict_proba(model, X) -> np.ndarray:
    """Predice probabilidades (home, draw, away)."""
    if hasattr(model, 'predict_proba'):
        return model.predict_proba(X)
    else:
        # XGBoost-style fallback
        return model.predict_proba(X)


def evaluate(predicted_probs: np.ndarray, y_true: np.ndarray) -> Dict[str, float]:
    """Calcula accuracy y Brier score."""
    preds = predicted_probs.argmax(axis=1)
    acc = (preds == y_true).mean()

    # Brier (multiclass)
    one_hot = np.eye(3)[y_true]
    brier = ((predicted_probs - one_hot) ** 2).sum(axis=1).mean()

    return {
        'accuracy': float(acc * 100),
        'brier': float(brier),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--train-start', default='2024-01-01')
    parser.add_argument('--train-end', default='2024-12-31')
    parser.add_argument('--test-start', default='2025-01-01')
    parser.add_argument('--test-end', default='2025-12-31')
    parser.add_argument('--model', default='xgb', choices=['xgb', 'lr', 'xgb_tiny'])
    parser.add_argument('--out', default='data/stacking_result.json')
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))

    print(f"\n📊 Cacheando train ({args.train_start} → {args.train_end})...")
    train_data = cache_predictions(conn, args.train_start, args.train_end)

    print(f"\n📊 Cacheando test ({args.test_start} → {args.test_end})...")
    test_data = cache_predictions(conn, args.test_start, args.test_end)

    X_train, y_train = to_xy(train_data)
    X_test, y_test = to_xy(test_data)

    print(f"\n🧠 Train set: {X_train.shape}")
    print(f"   Test set:  {X_test.shape}")

    # Baseline: ensemble base (linear con pesos)
    print(f"\n📈 Baseline: ensemble base (xg=0.55, elo=0.225, dc=0.135, heur=0.09)")
    baseline_probs = np.zeros((len(test_data), 3))
    for i, r in enumerate(test_data):
        baseline_probs[i, 0] = (
            r['xg_home'] * 0.55 + r['elo_home'] * 0.225 +
            r['dc_home'] * 0.135 + r['heur_home'] * 0.09
        )
        baseline_probs[i, 1] = (
            r['xg_draw'] * 0.55 + r['elo_draw'] * 0.225 +
            r['dc_draw'] * 0.135 + r['heur_draw'] * 0.09
        )
        baseline_probs[i, 2] = (
            r['xg_away'] * 0.55 + r['elo_away'] * 0.225 +
            r['dc_away'] * 0.135 + r['heur_away'] * 0.09
        )
    # Normalizar
    baseline_probs = baseline_probs / baseline_probs.sum(axis=1, keepdims=True)

    base_metrics = evaluate(baseline_probs, y_test)
    print(f"   Accuracy: {base_metrics['accuracy']:.2f}%")
    print(f"   Brier:    {base_metrics['brier']:.4f}")

    # Meta-learner
    print(f"\n🧠 Entrenando meta-learner ({args.model})...")
    print(f"   X_train.shape={X_train.shape}, X_train.dtype={X_train.dtype}")
    print(f"   y_train.shape={y_train.shape}, y_train unique={np.unique(y_train, return_counts=True)}")
    model = train_meta_learner(X_train, y_train, model_type=args.model)

    # Evaluar en train (overfitting check)
    train_probs = predict_proba(model, X_train)
    train_metrics = evaluate(train_probs, y_train)
    print(f"\n   Train acc: {train_metrics['accuracy']:.2f}%  (overfitting check)")

    # Evaluar en test
    test_probs = predict_proba(model, X_test)
    test_metrics = evaluate(test_probs, y_test)
    print(f"\n   Test acc:  {test_metrics['accuracy']:.2f}%")
    print(f"   Test Brier: {test_metrics['brier']:.4f}")

    # Comparar
    print("\n" + "=" * 70)
    print("📊 COMPARACIÓN: ENSEMBLE BASE vs STACKING")
    print("=" * 70)
    print(f"  Ensemble base:  acc={base_metrics['accuracy']:.2f}%  brier={base_metrics['brier']:.4f}")
    print(f"  Stacking {args.model}:  acc={test_metrics['accuracy']:.2f}%  brier={test_metrics['brier']:.4f}")
    delta_acc = test_metrics['accuracy'] - base_metrics['accuracy']
    delta_brier = test_metrics['brier'] - base_metrics['brier']
    print(f"  Δ:               acc={delta_acc:+.2f}pp  brier={delta_brier:+.4f}")
    print("=" * 70)

    if delta_acc > 0:
        print(f"\n✅ Stacking MEJORA accuracy en {delta_acc:.2f}pp")
    elif delta_acc < -0.5:
        print(f"\n❌ Stacking EMPEORA accuracy en {-delta_acc:.2f}pp (overfitting)")
    else:
        print(f"\n🟡 Stacking NEUTRO (Δ = {delta_acc:.2f}pp)")

    # Guardar resultados
    with open(PROJECT_ROOT / args.out, "w") as f:
        json.dump({
            "model_type": args.model,
            "train_range": [args.train_start, args.train_end],
            "test_range": [args.test_start, args.test_end],
            "n_train": int(len(train_data)),
            "n_test": int(len(test_data)),
            "baseline": base_metrics,
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
            "delta_acc_pp": round(delta_acc, 2),
            "delta_brier": round(delta_brier, 4),
        }, f, indent=2)
    print(f"\n  Guardado en: {args.out}")


if __name__ == "__main__":
    main()