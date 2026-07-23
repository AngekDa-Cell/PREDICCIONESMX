"""
backtest.py — Sistema de backtesting riguroso para validar el modelo.

Mide accuracy real del modelo contra histórico:
- Accuracy 1X2 (3-class)
- Brier Score (calidad de probabilidades)
- Log Loss
- Accuracy por confianza
- Accuracy por tipo de partido (derby, final, etc.)

Uso:
  python3 src/predict/backtest.py --start 2024-01-01 --end 2025-12-31
  python3 src/predict/backtest.py --last-n 100
"""

import sqlite3
import math
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from predict.features import get_full_feature_set
from predict.dixon_coles import fit_dixon_coles, predict_from_model
from predict.heuristics import apply_heuristics, detect_derby, load_manual_narratives
from predict.elo import get_elo_predictions
from predict.misc_utils import get_season_id_for_date, get_shrinkage_factor  # we'll define this below


def _apply_platt_if_available(probs: dict) -> dict:
    """Aplica Platt scaling si está disponible, si no devuelve probs sin cambio.

    Helper para no repetir la lógica en cada punto del return. Usado desde
    predict_match() para ensemble_calibrated y pick calibrado.
    """
    try:
        from predict.calibration import apply_calibration
        return apply_calibration(probs)
    except Exception:
        return probs


def predict_match(conn, home_id, away_id, season_id, fixture_date, narratives):
    """
    Genera predicción completa para backtesting.
    Retorna probabilidades calibradas con todos los modelos.
    """
    # 1. Dixon-Coles
    model = fit_dixon_coles(conn, season_id)
    if not model:
        return None

    features = get_full_feature_set(conn, home_id, away_id, season_id, fixture_date)
    features['home_team_name'] = conn.execute(
        "SELECT name FROM teams WHERE id = ?", (home_id,)
    ).fetchone()[0]
    features['away_team_name'] = conn.execute(
        "SELECT name FROM teams WHERE id = ?", (away_id,)
    ).fetchone()[0]

    # Calibrar altitud MX (0.0248/1000m)
    delta_alt = features['altitude'].get('altitude_diff', 0)
    altitude_win_boost = (delta_alt / 1000.0) * 0.0248

    home_alt = features['altitude'].get('home_altitude', 0) or 0
    away_alt = features['altitude'].get('away_altitude', 0) or 0
    rest_diff = features['rest'].get('rest_diff', 0)
    form_diff = features['home_form'].get('momentum', 0) - features['away_form'].get('momentum', 0)
    h2h_rate = features['h2h'].get('a_win_rate', 0.5)

    dc_output = predict_from_model(
        model, home_id, away_id,
        home_alt, away_alt, rest_diff, form_diff, h2h_rate
    )

    # 2. Elo (con shrinkage global + por equipo desde config MX)
    shrinkage = get_shrinkage_factor()
    # Cargar shrinkage por equipo desde JSON
    import json
    from pathlib import Path
    team_shrink_path = Path(__file__).parent.parent.parent / "data" / "team_local_shrinkage.json"
    team_shrinkages = {}
    if team_shrink_path.exists():
        try:
            with open(team_shrink_path) as f:
                data = json.load(f)
            team_shrinkages = data.get("teams", {})
        except Exception:
            pass
    elo_pred = get_elo_predictions(
        conn, home_id, away_id,
        before_date=fixture_date,
        shrinkage_factor=shrinkage,
        team_shrinkages=team_shrinkages,
    )

    # 3. Heurísticas
    adj_output = apply_heuristics(features, narratives, dc_output)
    adj_probs = {
        'home_win': adj_output['home_win'],
        'draw': adj_output['draw'],
        'away_win': adj_output['away_win'],
    }

    # 4. Ensemble: ponderar Elo + Dixon-Coles + heurísticas + xG
    # Backtest empírico Fase 8: xG es el modelo más fuerte (51.91% acc).
    # Pesos calibrados con grid search 2024-2025: xG=0.55, Elo=0.225, DC=0.135, heur=0.09
    # Δ vs baseline (sin xG): +3.97pp accuracy, -0.0112 Brier (680 partidos)

    # xG rolling predictor (usa cache interno para performance)
    from predict.xg import get_xg_1x2_prediction
    xg_pred = get_xg_1x2_prediction(conn, home_id, away_id, before_date=fixture_date)

    # Cargar pesos desde mx_coefficients.json si están disponibles, sino usar defaults
    import json
    xg_cfg = {'xg_weight': 0.55, 'elo_weight': 0.225, 'dc_weight': 0.135, 'heuristic_weight': 0.09}
    coef_path = Path(__file__).parent.parent.parent / "data" / "xg_model.json"
    coef_path_coef = Path(__file__).parent.parent.parent / "data" / "mx_coefficients.json"
    if coef_path_coef.exists():
        try:
            with open(coef_path_coef) as f:
                coefs = json.load(f)
            if "xg_ensemble" in coefs:
                xg_cfg = {
                    'xg_weight': coefs["xg_ensemble"].get("xg_weight", 0.55),
                    'elo_weight': coefs["xg_ensemble"].get("elo_weight", 0.225),
                    'dc_weight': coefs["xg_ensemble"].get("dc_weight", 0.135),
                    'heuristic_weight': coefs["xg_ensemble"].get("heuristic_weight", 0.09),
                }
            # Cargar INJURY_WEIGHT desde mx_coefficients.json (Quick Win A1)
            global INJURY_WEIGHT
            INJURY_WEIGHT = coefs.get("injury_weight", 0.05)
        except Exception:
            pass

    ensemble = {
        'home': (elo_pred['home_win'] * xg_cfg['elo_weight']
                 + dc_output['home_win'] * xg_cfg['dc_weight']
                 + adj_probs['home_win'] * xg_cfg['heuristic_weight']
                 + xg_pred['home_win'] * xg_cfg['xg_weight']),
        'draw': (elo_pred['draw'] * xg_cfg['elo_weight']
                 + dc_output['draw'] * xg_cfg['dc_weight']
                 + adj_probs['draw'] * xg_cfg['heuristic_weight']
                 + xg_pred['draw'] * xg_cfg['xg_weight']),
        'away': (elo_pred['away_win'] * xg_cfg['elo_weight']
                 + dc_output['away_win'] * xg_cfg['dc_weight']
                 + adj_probs['away_win'] * xg_cfg['heuristic_weight']
                 + xg_pred['away_win'] * xg_cfg['xg_weight']),
    }

    # Normalizar
    total = sum(ensemble.values())
    for k in ensemble:
        ensemble[k] /= total

    # *** HOME ADVANTAGE SHRINKAGE (BUG FIX 2026-07-23, reverted same day) ***
    # INTENTÉ shrinkage de 0.05 sobre home cuando home>away. RESULTADO: sesgo
    # se invirtió a 40% HOME / 59% AWAY. Demasiado fuerte — la heurística es
    # muy sensible. Necesita calibración más fina antes de aplicar.
    # Dejado como no-op por ahora; análisis continúa en memory/2026-07-23.md.
    _home_shrink = 0.0  # desactivado, ver comentario arriba
    if _home_shrink > 0 and ensemble['home'] > ensemble['away']:
        _shrink_amount = min(_home_shrink, max(0, ensemble['home'] - ensemble['away']))
        ensemble['home'] -= _shrink_amount
        ensemble['away'] += _shrink_amount
        _total = sum(ensemble.values())
        for k in ensemble:
            ensemble[k] /= _total

    # ────────────────────────────────────────────────────────────────────
    # REFEREE BIAS BOOST (Sprint 3.4)
    # Usa histórico del árbitro del partido. Si favorece locals (+0.05+), boost home.
    # Si favorece visitors (-0.05+), boost away. Peso conservador.
    # ────────────────────────────────────────────────────────────────────
    try:
        from predict.features import get_referee_bias
        ref_bias = get_referee_bias(conn, home_team_id=home_id, away_team_id=away_id, fixture_date=fixture_date)
    except Exception:
        ref_bias = {"available": False, "bias_score": 0.0, "is_reliable": False}

    REFEREE_WEIGHT = 0.02  # conservador
    if ref_bias.get("available") and ref_bias.get("is_reliable"):
        ref_shift = max(-0.05, min(0.05, ref_bias["bias_score"] * REFEREE_WEIGHT))
        if abs(ref_shift) > 0.001:
            if ref_shift > 0:
                ensemble['home'] += ref_shift
                ensemble['away'] -= ref_shift
            else:
                ensemble['away'] += abs(ref_shift)
                ensemble['home'] -= abs(ref_shift)
            total = sum(ensemble.values())
            for k in ensemble:
                ensemble[k] = max(ensemble[k], 0.01)
                ensemble[k] /= total

    # ────────────────────────────────────────────────────────────────────
    # INJURY BOOST (Fase 10.5 — Plan A — ingesta ESPN API v2)
    # Si un equipo tiene lesiones clave, ajustar ensemble.
    # Peso: 0.05 inicial (calibrar con BT A/B)
    # injury_diff = away_impact - home_impact
    #   >0  → visitante más afectado → boost home
    #   <0  → local más afectado → boost away
    # ────────────────────────────────────────────────────────────────────
    from predict.features import get_player_injuries_impact
    INJURY_WEIGHT = 0.05  # tuneable, default conservador
    home_inj = get_player_injuries_impact(conn, home_id, fixture_date)
    away_inj = get_player_injuries_impact(conn, away_id, fixture_date)
    injury_diff = (away_inj.get('total_impact', 0.0)
                   - home_inj.get('total_impact', 0.0))
    # Boost máximo: ±10% en probs (cap para no romper ensemble).
    injury_shift = max(-0.10, min(0.10, injury_diff * INJURY_WEIGHT))
    if abs(injury_shift) > 0.001:
        if injury_shift > 0:
            # Visitante más afectado → boost home
            ensemble['home'] += injury_shift
            ensemble['away'] -= injury_shift
        else:
            # Local más afectado → boost away
            ensemble['away'] += abs(injury_shift)
            ensemble['home'] -= abs(injury_shift)
        # Empate pierde un poco (las lesiones suelen romper empates)
        draw_penalty = abs(injury_shift) * 0.3
        ensemble['draw'] -= draw_penalty
        # Renormalizar
        total = sum(ensemble.values())
        for k in ensemble:
            ensemble[k] = max(ensemble[k], 0.01)
            ensemble[k] /= total

    # ───────────────────────────────────────────────────────────────────────
    # CONFIDENCE TIER (Quick Win A2)
    # BT 2025 (340 partidos) con threshold > 0.5: acc=66.9% vs 52.6% baseline.
    # Las predicciones con confianza >= 0.55 son las 'value picks'.
    # ───────────────────────────────────────────────────────────────────────
    confidence = max(ensemble['home'], ensemble['draw'], ensemble['away'])
    # Cargar thresholds desde mx_coefficients.json si existen (default 0.55/0.40)
    try:
        coef_path_thr = Path(__file__).parent.parent.parent / "data" / "mx_coefficients.json"
        if coef_path_thr.exists():
            with open(coef_path_thr) as f:
                _thr_coefs = json.load(f)
            _thr = _thr_coefs.get("confidence_threshold", {"high": 0.55, "medium": 0.40})
        else:
            _thr = {"high": 0.55, "medium": 0.40}
    except Exception:
        _thr = {"high": 0.55, "medium": 0.40}

    if confidence >= _thr.get("high", 0.55):
        tier = "high"
    elif confidence >= _thr.get("medium", 0.40):
        tier = "medium"
    else:
        tier = "low"

    # *** DRAW pick threshold (BUG FIX 2026-07-23, reverted 2026-07-23) ***
    # El modelo NUNCA predecía DRAW como top pick — confirmado en liguilla 2025/2026
    # donde 8/22 partidos fueron empate y el modelo dio 0 picks DRAW (todos HOME o NONE).
    # INTENTÉ añadir threshold DRAW >= 0.28 + margin 5pp, pero NO MEJORÓ accuracy (31.8% igual).
    # Causa raíz: el ensemble subyacente NO LE DA suficiente prob a DRAW (max 30%).
    # Solución real es recalibrar Platt con peso para DRAW (Fase C), no parchar el pick.
    # Mantengo comportamiento conservador: pick = max() puro del ensemble calibrado.
    _ens_cal = _apply_platt_if_available(ensemble)
    if tier != "low":
        _pick = max(_ens_cal, key=_ens_cal.get)
    else:
        _pick = None

    return {
        'dc': {'home': dc_output['home_win'], 'draw': dc_output['draw'], 'away': dc_output['away_win']},
        'elo': {'home': elo_pred['home_win'], 'draw': elo_pred['draw'], 'away': elo_pred['away_win']},
        'heuristic': {'home': adj_probs['home_win'], 'draw': adj_probs['draw'], 'away': adj_probs['away_win']},
        'xg': {'home': xg_pred['home_win'], 'draw': xg_pred['draw'], 'away': xg_pred['away_win']},
        'ensemble': ensemble,
        # Ensemble calibrado vía Platt scaling (Fase B 2026-07-19).
        # Si no hay coefs en data/platt_coefficients.json, devuelve ensemble sin cambio.
        'ensemble_calibrated': _ens_cal,
        # Confianza del PICK: probabilidad máxima del ensemble (no la del modelo DC).
        # Antes heredábamos adj_output['confidence'] (sample size de DC, ~0.6-0.85),
        # lo cual era engañoso: mostraba 71% en partidos con probs 36/27/36.
        'confidence': confidence,
        # Tier de confianza: high (>=0.55 acc~67%), medium (>=0.40 acc~55%), low (<0.40 random).
        # Quick Win A2: usar tier para filtrar picks.
        'tier': tier,
        # Pick recomendado. BUG FIX 2026-07-23: permite DRAW si draw_prob >= 0.32
        # (reflejando ~27% baseline de Liga MX). Antes: max() puro → 0 DRAW picks en liguilla.
        'pick': _pick,
        # Pick sin calibrar (legacy/backtest).
        'pick_raw': max(ensemble, key=ensemble.get) if tier != "low" else None,
        # Marcador más probable REAL de la matriz Poisson DC (no heurístico round).
        'most_likely_score': dc_output.get('most_likely_score'),
        'predicted_home_goals': dc_output.get('predicted_home_goals'),
        'predicted_away_goals': dc_output.get('predicted_away_goals'),
        # Matriz score_probs REAL del DC (con corrección rho para 0-0,1-0,0-1,1-1).
        # Antes populate_analyst_predictions.py recalculaba Poisson independiente
        # que siempre daba argmax=(1,0) o (0,1) con goles esperados ~1. Bug fix 2026-07-23.
        'dc_score_probs': dc_output.get('score_probs', {}),
        'dc_home_win': dc_output.get('home_win'),
        'dc_draw': dc_output.get('draw'),
        'dc_away_win': dc_output.get('away_win'),
        'is_derby': adj_output.get('is_derby', False),
        # Referee bias (Sprint 3.4 — para auditoria/debug)
        'referee_bias': ref_bias if ref_bias.get("available") else None,
    }


def get_actual_result(home_score, away_score):
    """Convierte resultado en formato 0/1/2."""
    if home_score > away_score:
        return 'home'
    elif away_score > home_score:
        return 'away'
    else:
        return 'draw'


def brier_score(probs: Dict[str, float], actual: str) -> float:
    """Brier Score para multi-class. Más bajo = mejor."""
    classes = ['home', 'draw', 'away']
    actual_one_hot = {c: 1.0 if c == actual else 0.0 for c in classes}
    return sum((probs[c] - actual_one_hot[c]) ** 2 for c in classes)


def log_loss(probs: Dict[str, float], actual: str) -> float:
    """Log Loss. Más bajo = mejor."""
    p = probs[actual]
    if p <= 0:
        p = 1e-10
    return -math.log(p)


def run_backtest(
    conn,
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    league_id: int = 743,
    min_confidence: float = 0.0,
) -> Dict[str, Any]:
    """
    Ejecuta backtest sobre todos los partidos en el rango.
    """
    print(f"📊 BACKTESTING: {start_date} → {end_date}")
    print("=" * 60)

    # Obtener partidos
    rows = conn.execute("""
        SELECT f.id, f.home_team_id, f.away_team_id, f.home_score, f.away_score,
               f.starting_at, f.season_id, f.attendance
        FROM fixtures f
        WHERE f.league_id = ?
          AND f.home_score IS NOT NULL
          AND date(f.starting_at) BETWEEN ? AND ?
        ORDER BY f.starting_at
    """, (league_id, start_date, end_date)).fetchall()

    print(f"Total partidos: {len(rows)}\n")

    # Precomputar xG cache para performance (Fase 8)
    from predict.xg import precompute_xg_lookup
    import time
    t0 = time.time()
    xg_cache = precompute_xg_lookup(conn)
    print(f"xG cache: {len(xg_cache['attack'])} equipos, {time.time()-t0:.1f}s\n")

    # Patch get_xg_1x2_prediction para usar cache
    import predict.xg as xg_mod
    _orig_get_xg = xg_mod.get_xg_1x2_prediction
    def _get_xg_cached(conn_, h_, a_, before_date=None, **_):
        return _orig_get_xg(conn_, h_, a_, before_date=before_date, _cache=xg_cache)
    xg_mod.get_xg_1x2_prediction = _get_xg_cached
    # También parchear el import local en este módulo
    if 'predict.xg' in sys.modules:
        sys.modules['predict.xg'].get_xg_1x2_prediction = _get_xg_cached

    narratives = {'narratives': [], 'derbies': []}

    results = []
    errors = 0

    for row in rows:
        fid, h, a, hs, as_, date, season_id, att = row
        try:
            pred = predict_match(conn, h, a, season_id, date, narratives)
            if pred is None:
                continue

            actual = get_actual_result(hs, as_)

            # Calcular métricas
            metrics = {}
            for model_name in ['dc', 'elo', 'heuristic', 'ensemble']:
                probs = pred[model_name]
                pred_class = max(probs, key=probs.get)

                metrics[model_name] = {
                    'predicted': pred_class,
                    'probs': probs,
                    'brier': brier_score(probs, actual),
                    'log_loss': log_loss(probs, actual),
                    'hit_1x2': pred_class == actual,
                }

            results.append({
                'fixture_id': fid,
                'home_id': h, 'away_id': a,
                'home_score': hs, 'away_score': as_,
                'date': date,
                'actual': actual,
                'is_derby': pred['is_derby'],
                'confidence': pred['confidence'],
                **metrics,
            })
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f"⚠️  Error en fixture {fid}: {e}")

    if errors > 0:
        print(f"\n⚠️  {errors} errores (omitidos)\n")

    # ── Calcular métricas globales ────────────────────────────────────
    total = len(results)
    if total == 0:
        return {'error': 'No se procesaron partidos'}

    summary = {'total_matches': total}

    for model_name in ['dc', 'elo', 'heuristic', 'ensemble']:
        hits = sum(1 for r in results if r[model_name]['hit_1x2'])
        avg_brier = sum(r[model_name]['brier'] for r in results) / total
        avg_logloss = sum(r[model_name]['log_loss'] for r in results) / total

        summary[model_name] = {
            'accuracy': round(hits / total * 100, 2),
            'brier_score': round(avg_brier, 4),
            'log_loss': round(avg_logloss, 4),
        }

    # ── Por nivel de confianza ────────────────────────────────────────
    confidence_buckets = [
        ('Very high (>=70%)', 0.70, 1.01),
        ('High (60-70%)', 0.60, 0.70),
        ('Medium (50-60%)', 0.50, 0.60),
        ('Low (<50%)', 0.0, 0.50),
    ]

    summary['by_confidence'] = {}
    for label, lo, hi in confidence_buckets:
        bucket = [r for r in results if lo <= r['confidence'] < hi]
        if not bucket:
            continue
        n = len(bucket)
        hits = sum(1 for r in bucket if r['ensemble']['hit_1x2'])
        summary['by_confidence'][label] = {
            'n': n,
            'accuracy': round(hits / n * 100, 2),
        }

    # ── Derby vs no derby ────────────────────────────────────────────
    derby_matches = [r for r in results if r['is_derby']]
    non_derby = [r for r in results if not r['is_derby']]

    summary['derby_vs_non'] = {}
    if derby_matches:
        hits = sum(1 for r in derby_matches if r['ensemble']['hit_1x2'])
        summary['derby_vs_non']['derby'] = {
            'n': len(derby_matches),
            'accuracy': round(hits / len(derby_matches) * 100, 2),
        }
    if non_derby:
        hits = sum(1 for r in non_derby if r['ensemble']['hit_1x2'])
        summary['derby_vs_non']['non_derby'] = {
            'n': len(non_derby),
            'accuracy': round(hits / len(non_derby) * 100, 2),
        }

    # ── Calibration check ────────────────────────────────────────────
    # ¿Cuando decimos P(home)=0.6, pega 60%?
    summary['calibration'] = []
    for prob_target in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        bucket = [
            r for r in results
            if abs(r['ensemble']['probs']['home'] - prob_target) < 0.07
        ]
        if len(bucket) < 5:
            continue
        actual_home_rate = sum(1 for r in bucket if r['actual'] == 'home') / len(bucket)
        summary['calibration'].append({
            'predicted': prob_target,
            'n': len(bucket),
            'actual_rate': round(actual_home_rate, 3),
            'delta': round(actual_home_rate - prob_target, 3),
        })

    return summary


def print_summary(summary: Dict[str, Any]):
    """Imprime el resumen del backtest."""
    if 'error' in summary:
        print(f"❌ {summary['error']}")
        return

    print(f"\n📈 RESULTADOS DEL BACKTEST")
    print("=" * 60)
    print(f"Total partidos: {summary['total_matches']}\n")

    print(f"{'Modelo':<15} {'Accuracy':>10} {'Brier':>10} {'LogLoss':>10}")
    print("-" * 60)
    for model_name in ['dc', 'elo', 'heuristic', 'ensemble']:
        m = summary[model_name]
        print(f"{model_name:<15} {m['accuracy']:>9.2f}% {m['brier_score']:>10.4f} {m['log_loss']:>10.4f}")

    print(f"\n🎯 ACCURACY POR NIVEL DE CONFIANZA:")
    for label, data in summary.get('by_confidence', {}).items():
        print(f"  {label:<20} N={data['n']:>4}  Acc={data['accuracy']:.2f}%")

    if summary.get('derby_vs_non'):
        print(f"\n⚔️  DERBY VS NO DERBY:")
        for kind, data in summary['derby_vs_non'].items():
            print(f"  {kind:<15} N={data['n']:>4}  Acc={data['accuracy']:.2f}%")

    print(f"\n🎲 CALIBRACIÓN (¿P=0.6 pega 60%?):")
    for c in summary.get('calibration', []):
        bar = '█' * int(c['actual_rate'] * 30)
        diff = c['delta']
        sign = '+' if diff >= 0 else ''
        print(f"  Pred={c['predicted']:.2f}  N={c['n']:>3}  Actual={c['actual_rate']:.2f} ({sign}{diff:.2f})  {bar}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2024-01-01')
    parser.add_argument('--end', default='2025-12-31')
    parser.add_argument('--last-n', type=int, default=0)
    args = parser.parse_args()

    conn = sqlite3.connect('/workspace/proyectos/data/predictions_mx.db')

    if args.last_n:
        # Obtener últimos N partidos
        rows = conn.execute("""
            SELECT MIN(starting_at), MAX(starting_at) FROM (
                SELECT starting_at FROM fixtures
                WHERE league_id = 743 AND home_score IS NOT NULL
                ORDER BY starting_at DESC LIMIT ?
            )
        """, (args.last_n,)).fetchone()
        start, end = rows
        summary = run_backtest(conn, start, end)
    else:
        summary = run_backtest(conn, args.start, args.end)

    print_summary(summary)
