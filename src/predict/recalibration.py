"""
recalibration.py — Recalibración de probabilidades del ensemble.

Problema conocido: el modelo es overconfident cuando predice ≥70%
(accuracy real solo 43% en ese bucket).

Soluciones implementadas:
1. Temperature Scaling — divide logits por T óptimo (multi-class simple)
2. Platt Scaling binario — sigmoid(A*logit(P) + B) por outcome

Temperatura:
- T=1: sin cambios
- T>1: suaviza probabilidades (menos overconfident)
- T<1: sharpen

Cómo se entrena:
- Correr backtest → juntar (probs_predichas, resultado_real) por partido
- Minimizar NLL sobre set de validación
- Guardar T en disco

Uso:
  python3 src/predict/calibrate.py --start 2024-01-01 --end 2025-12-31
  python3 src/predict/cli.py --home "X" --away "Y" --recalibrated
"""

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import sqlite3

PROJECT_ROOT = Path(__file__).parent.parent.parent
CALIBRATION_PATH = PROJECT_ROOT / "data" / "mx_recalibration.json"


# ─────────────────────────────────────────────────────────────────────────────
# TEMPERATURE SCALING
# ─────────────────────────────────────────────────────────────────────────────

def softmax(logits: List[float]) -> List[float]:
    """Softmax numéricamente estable."""
    m = max(logits)
    exps = [math.exp(l - m) for l in logits]
    s = sum(exps)
    return [e / s for e in exps]


def apply_temperature(probs: Dict[str, float], T: float = 1.0) -> Dict[str, float]:
    """
    Aplica temperature scaling a probabilidades 1X2.

    Args:
        probs: {home_win, draw, away_win}
        T: temperatura (1.0 = sin cambios)

    Returns:
        Probabilidades recalibradas (mismo dict, valores ajustados)
    """
    if T == 1.0:
        return probs

    # Convertir a logits
    eps = 1e-12
    logits = [
        math.log(max(probs['home_win'], eps)),
        math.log(max(probs['draw'], eps)),
        math.log(max(probs['away_win'], eps)),
    ]

    # Aplicar temperatura
    scaled = [l / T for l in logits]

    # Softmax
    new_probs = softmax(scaled)

    return {
        'home_win': new_probs[0],
        'draw': new_probs[1],
        'away_win': new_probs[2],
    }


def negative_log_likelihood(
    T: float,
    predictions: List[Dict[str, float]],
    actuals: List[int]  # 0=home, 1=draw, 2=away
) -> float:
    """NLL para optimización de T."""
    nll = 0.0
    n = len(predictions)
    for pred, actual in zip(predictions, actuals):
        new_probs = apply_temperature(pred, T)
        p = new_probs[['home_win', 'draw', 'away_win'][actual]]
        nll -= math.log(max(p, 1e-12))
    return nll / n


def find_optimal_temperature(
    predictions: List[Dict[str, float]],
    actuals: List[int],
    T_min: float = 0.5,
    T_max: float = 3.0,
    step: float = 0.05,
) -> Tuple[float, float]:
    """
    Encuentra T óptimo por grid search.

    Returns:
        (T_optimo, NLL_min)
    """
    best_T = 1.0
    best_nll = float('inf')

    T = T_min
    while T <= T_max:
        nll = negative_log_likelihood(T, predictions, actuals)
        if nll < best_nll:
            best_nll = nll
            best_T = T
        T += step

    return best_T, best_nll


# ─────────────────────────────────────────────────────────────────────────────
# PLATT SCALING (binary, per-outcome)
# ─────────────────────────────────────────────────────────────────────────────

def sigmoid(x: float) -> float:
    """Sigmoid numéricamente estable."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        ez = math.exp(x)
        return ez / (1.0 + ez)


def fit_platt_binary(
    predictions: List[float],
    actuals: List[int],  # 0 o 1
    lr: float = 0.01,
    epochs: int = 500,
) -> Tuple[float, float]:
    """
    Ajusta Platt scaling: P'(x) = sigmoid(A * logit(x) + B).

    Por descenso de gradiente simple.

    Returns:
        (A, B)
    """
    A = 1.0
    B = 0.0

    for epoch in range(epochs):
        # Acumular gradientes
        grad_A = 0.0
        grad_B = 0.0

        for p, y in zip(predictions, actuals):
            # Clip p
            p = max(min(p, 1 - 1e-9), 1e-9)
            logit = math.log(p / (1 - p))
            sigmoid_axb = sigmoid(A * logit + B)
            error = sigmoid_axb - y
            grad_A += error * logit
            grad_B += error

        n = len(predictions)
        A -= lr * grad_A / n
        B -= lr * grad_B / n

    return A, B


def apply_platt(probs: List[float], A: float, B: float) -> List[float]:
    """Aplica Platt scaling a una lista de probabilidades binarias."""
    result = []
    for p in probs:
        p = max(min(p, 1 - 1e-9), 1e-9)
        logit = math.log(p / (1 - p))
        result.append(sigmoid(A * logit + B))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CALIBRATION STORAGE
# ─────────────────────────────────────────────────────────────────────────────

def save_calibration(
    temperature: float,
    nll_before: float,
    nll_after: float,
    n_samples: int,
    method: str = "temperature",
    platt_params: Optional[Dict[str, Tuple[float, float]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Guarda parámetros de calibración en disco."""
    data = {
        "method": method,
        "temperature": temperature,
        "platt": platt_params or {},
        "metrics": {
            "nll_before": nll_before,
            "nll_after": nll_after,
            "n_samples": n_samples,
        },
        "metadata": metadata or {},
        "generated_at": str(Path(__file__).stat().st_mtime),  # placeholder
    }
    CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CALIBRATION_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Calibración guardada en {CALIBRATION_PATH}")


def load_calibration() -> Optional[Dict[str, Any]]:
    """Carga calibración desde disco. Retorna None si no existe."""
    if not CALIBRATION_PATH.exists():
        return None
    with open(CALIBRATION_PATH) as f:
        return json.load(f)


def apply_calibration(probs: Dict[str, float]) -> Dict[str, float]:
    """
    Aplica la calibración guardada a las probabilidades.

    Si no hay calibración, retorna las probabilidades sin cambios.
    """
    cal = load_calibration()
    if not cal:
        return probs

    if cal["method"] == "temperature":
        return apply_temperature(probs, cal["temperature"])
    elif cal["method"] == "platt":
        # Aplicar Platt por outcome binario (1-vs-not-1, X-vs-not-X, 2-vs-not-2)
        new_probs = {}
        for outcome, key in [("home", "home_win"), ("draw", "draw"), ("away", "away_win")]:
            if outcome in cal.get("platt", {}):
                A, B = cal["platt"][outcome]
                new_probs[key] = sigmoid(A * math.log(max(probs[key], 1e-9) / (1 - max(probs[key], 1e-9))) + B)
            else:
                new_probs[key] = probs[key]
        # Renormalizar
        total = sum(new_probs.values())
        for k in new_probs:
            new_probs[k] /= total
        return new_probs

    return probs


# ─────────────────────────────────────────────────────────────────────────────
# CLI para calibrar
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--method", choices=["temperature", "platt"], default="temperature")
    parser.add_argument("--min-samples", type=int, default=100)
    args = parser.parse_args()

    # Importar backtest
    sys.path.insert(0, str(Path(__file__).parent))
    from backtest import predict_match

    DB_PATH = Path(__file__).parent.parent.parent / "data" / "predictions_mx.db"
    if not DB_PATH.exists():
        print(f"❌ BD no encontrada: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Obtener fixtures con resultado
    fixtures = conn.execute("""
        SELECT id, season_id, home_team_id, away_team_id, starting_at,
               home_score, away_score
        FROM fixtures
        WHERE league_id = 743
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND starting_at >= ?
          AND starting_at < ?
        ORDER BY starting_at
    """, (args.start, args.end)).fetchall()

    print(f"📊 {len(fixtures)} fixtures en [{args.start}, {args.end})")

    if len(fixtures) < args.min_samples:
        print(f"❌ Muy pocos samples ({len(fixtures)} < {args.min_samples})")
        sys.exit(1)

    # Generar predicciones
    predictions = []
    actuals = []  # 0=home, 1=draw, 2=away

    from predict.misc_utils import get_season_id_for_date
    from predict.heuristics import load_manual_narratives

    season_cache = {}
    narratives_cache = {}

    for i, f in enumerate(fixtures):
        if i % 50 == 0:
            print(f"  Progreso: {i}/{len(fixtures)}...")

        # Determinar season_id
        if f['season_id'] not in season_cache:
            season_cache[f['season_id']] = f['season_id']
        season_id = f['season_id']

        # Narrativas por temporada
        if season_id not in narratives_cache:
            season_name = conn.execute(
                "SELECT name FROM seasons WHERE id = ?", (season_id,)
            ).fetchone()
            if season_name:
                narratives_cache[season_id] = load_manual_narratives(season_name['name'].split('/')[0].strip())
            else:
                narratives_cache[season_id] = load_manual_narratives()

        try:
            pred = predict_match(
                conn,
                home_id=f['home_team_id'],
                away_id=f['away_team_id'],
                season_id=season_id,
                fixture_date=str(f['starting_at']),
                narratives=narratives_cache[season_id],
            )
            if pred is None:
                continue
            ensemble = pred['ensemble']
            predictions.append({
                'home_win': ensemble['home'],
                'draw': ensemble['draw'],
                'away_win': ensemble['away'],
            })
            # Actual: 0=home, 1=draw, 2=away
            if f['home_score'] > f['away_score']:
                actuals.append(0)
            elif f['home_score'] < f['away_score']:
                actuals.append(2)
            else:
                actuals.append(1)
        except Exception as e:
            continue

    print(f"✅ {len(predictions)} predicciones generadas")

    # NLL base (sin recalibrar)
    nll_before = negative_log_likelihood(1.0, predictions, actuals)
    print(f"📈 NLL sin recalibrar (T=1.0): {nll_before:.4f}")

    if args.method == "temperature":
        T_opt, nll_after = find_optimal_temperature(predictions, actuals)
        print(f"📈 NLL recalibrado (T={T_opt:.2f}): {nll_after:.4f}")
        print(f"📈 Mejora: {nll_before - nll_after:.4f}")

        save_calibration(
            temperature=T_opt,
            nll_before=nll_before,
            nll_after=nll_after,
            n_samples=len(predictions),
            method="temperature",
            metadata={
                "start": args.start,
                "end": args.end,
            },
        )

    elif args.method == "platt":
        # Platt por outcome
        platt_params = {}
        outcomes = [("home", 0), ("draw", 1), ("away", 2)]

        for outcome, idx in outcomes:
            # Para outcome X, target = 1 si actual=X, 0 otherwise
            preds_binary = [p[['home_win', 'draw', 'away_win'][idx]] for p in predictions]
            actuals_binary = [1 if a == idx else 0 for a in actuals]
            A, B = fit_platt_binary(preds_binary, actuals_binary)
            platt_params[outcome] = (A, B)
            print(f"  {outcome}: A={A:.4f}, B={B:.4f}")

        # Evaluar con Platt
        new_predictions = []
        for p in predictions:
            new_p = {}
            for outcome, idx in outcomes:
                A, B = platt_params[outcome]
                p_i = p[['home_win', 'draw', 'away_win'][idx]]
                p_i_clipped = max(min(p_i, 1 - 1e-9), 1e-9)
                logit = math.log(p_i_clipped / (1 - p_i_clipped))
                new_p[['home_win', 'draw', 'away_win'][idx]] = sigmoid(A * logit + B)
            # Renormalizar
            total = sum(new_p.values())
            for k in new_p:
                new_p[k] /= total
            new_predictions.append(new_p)

        nll_after = negative_log_likelihood(1.0, new_predictions, actuals)
        print(f"📈 NLL recalibrado (Platt): {nll_after:.4f}")
        print(f"📈 Mejora: {nll_before - nll_after:.4f}")

        save_calibration(
            temperature=1.0,
            nll_before=nll_before,
            nll_after=nll_after,
            n_samples=len(predictions),
            method="platt",
            platt_params=platt_params,
            metadata={
                "start": args.start,
                "end": args.end,
            },
        )


if __name__ == "__main__":
    main()