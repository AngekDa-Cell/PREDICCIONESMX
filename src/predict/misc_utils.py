"""Utilities misceláneas para Predictions_MX."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


# Ruta al archivo de coeficientes MX calibrados
_COEFF_PATH = Path(__file__).parent.parent.parent / "data" / "mx_coefficients.json"


def get_season_id_for_date(conn: sqlite3.Connection, date_str: str, league_id: int = 743) -> Optional[int]:
    """Encuentra el season_id que contiene una fecha."""
    row = conn.execute("""
        SELECT id FROM seasons
        WHERE league_id = ?
          AND start_date <= ?
          AND (end_date IS NULL OR end_date >= ?)
        ORDER BY start_date DESC LIMIT 1
    """, (league_id, date_str, date_str)).fetchone()
    return row[0] if row else None


def load_mx_coefficients() -> Dict[str, Any]:
    """
    Carga los coeficientes calibrados para Liga MX.

    Returns:
        Dict con todos los coeficientes (altitude, rest_days, etc).
        Si el archivo no existe, retorna {}.
    """
    if not _COEFF_PATH.exists():
        return {}
    try:
        with open(_COEFF_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def get_shrinkage_factor() -> float:
    """
    Retorna el factor de shrinkage calibrado del Elo.
    Default 0.7 si no está configurado.
    """
    coeffs = load_mx_coefficients()
    return coeffs.get("elo_shrinkage", {}).get("factor", 0.7)
