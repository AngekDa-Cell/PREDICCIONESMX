"""
calibration.py — Platt scaling para calibrar probabilidades del ensemble.

Aplica Platt scaling (regresión logística por clase 1-vs-rest) a las
probabilidades crudas del ensemble. Lee coeficientes de
`data/platt_coefficients.json`. Si el archivo no existe o está vacío,
devuelve las probs sin cambio (modo degradado).

Uso:
    from predict.calibration import apply_calibration
    
    raw = pred["ensemble"]
    calibrated = apply_calibration(raw)
    # calibrated["home"] + calibrated["draw"] + calibrated["away"] == 1.0

Detalles:
    - 1-vs-rest Platt scaling: ajusta 3 regresiones logísticas (home vs resto, draw vs resto, away vs resto).
    - Renormalización: después de Platt, las 3 probs se renormalizan para sumar 1.0.
    - Coeficientes A, B ajustados vía maxima verosimilitud sobre n=1000 partidos (4 temporadas).
"""

import json
import math
from pathlib import Path
from typing import Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
COEFS_PATH = PROJECT_ROOT / "data" / "platt_coefficients.json"


def _sigmoid(x: float) -> float:
    """Sigmoide numéricamente estable."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


_coefs_cache: Optional[Dict[str, Dict[str, float]]] = None
_target_cache: Optional[str] = None
_disabled = False


def _load_coefficients() -> Optional[Dict[str, Dict[str, float]]]:
    """Carga coeficientes de Platt (cached). Devuelve None si no hay coefs."""
    global _coefs_cache, _target_cache, _disabled
    if _disabled:
        return None
    if _coefs_cache is not None:
        return _coefs_cache
    if not COEFS_PATH.exists():
        _disabled = True
        return None
    try:
        with open(COEFS_PATH) as f:
            data = json.load(f)
        coefs = data.get("_global_a_b")
        if not coefs or len(coefs) != 3:
            _disabled = True
            return None
        _coefs_cache = coefs
        _target_cache = data.get("_target")
        return _coefs_cache
    except Exception:
        _disabled = True
        return None


def get_target() -> Optional[str]:
    """Devuelve el target actual (ens/elo/xg/dc/heur) o None si no hay coefs."""
    _load_coefficients()
    return _target_cache


def reload_coefficients() -> None:
    """Fuerza recarga de coefs (útil después de re-fitting)."""
    global _coefs_cache, _target_cache, _disabled
    _coefs_cache = None
    _target_cache = None
    _disabled = False


def apply_calibration(probs: Dict[str, float]) -> Dict[str, float]:
    """Aplica Platt scaling a las probs de un partido.

    Args:
        probs: dict con keys 'home', 'draw', 'away' (probs crudas).

    Returns:
        dict con keys 'home', 'draw', 'away' (probs calibradas, suma=1).
        Si no hay coefs, devuelve probs sin cambio.
    """
    coefs = _load_coefficients()
    if coefs is None:
        return probs
    eps = 1e-12
    out = {}
    for cls in ("home", "draw", "away"):
        a = coefs[cls]["a"]
        b = coefs[cls]["b"]
        p = max(eps, min(1.0 - eps, probs[cls]))
        logit = math.log(p / (1.0 - p))
        out[cls] = _sigmoid(a * logit + b)
    # Renormalizar para que sumen 1.0
    total = sum(out.values())
    return {k: v / total for k, v in out.items()}


def is_enabled() -> bool:
    """True si Platt scaling está activo (coefs cargados)."""
    return _load_coefficients() is not None
