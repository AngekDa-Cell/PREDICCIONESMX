"""
conftest.py — Setup común para todos los tests.

Provee:
- Conexión a BD de testing (la misma BD, read-only para no romper nada)
- Equipos conocidos para usar en tests
- Fechas de referencia
"""
import pytest
import sqlite3
import os
import sys
from pathlib import Path

# Setup path para importar predict/
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# BD real (read-only en tests para no afectar datos)
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
LIGA_MX_ID = 743


@pytest.fixture(scope="session")
def db():
    """Conexión a la BD real (read-only)."""
    if not DB_PATH.exists():
        pytest.skip(f"BD no encontrada: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def conn(db):
    """Alias para consistencia con código."""
    return db


# Equipos conocidos (de los 19 en Liga MX)
TEAMS = {
    "america": 2687,        # Club América
    "chivas": 427,          # Guadalajara
    "cruz_azul": 2626,
    "pumas": 2989,
    "tigres": 609,
    "rayados": 2662,
    "atlas": 680,
    "leon": 10836,
    "santos": 2844,
    "pachuca": 10036,
    "toluca": 967,
    "necaxa": 3951,
    "san_luis": 15522,
    "juarez": 6335,
    "queretaro": 538,
    "puebla": 3849,
    "mazatlan": 247689,
    "tijuana": 11023,
    "monterrey": 2662,  # alias
}


@pytest.fixture
def team_ids():
    return TEAMS


@pytest.fixture
def mid_season_date():
    """Fecha mid-season 2024-2025 (muchos datos disponibles)."""
    return "2024-11-15"


@pytest.fixture
def end_season_date():
    """Fecha fin de temporada 2024/2025."""
    return "2025-05-15"