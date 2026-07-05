"""
config.py — Configuración centralizada del proyecto.

Lee variables de entorno desde `.env` (si existe) y expone constantes
tipadas para todo el sistema.

Cualquier valor sensible (tokens, paths privados) debe venir del .env,
NUNCA hardcoded en código fuente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


# =============================================================
# SportMonks — Configuración de la API
# =============================================================

@dataclass(frozen=True)
class SportMonksConfig:
    """Configuración del cliente SportMonks."""
    api_token: str
    base_url: str
    rate_limit_per_hour: int
    league_mexico_parent: int
    league_liga_mx: int
    league_liga_expansion: int

    @classmethod
    def from_env(cls) -> "SportMonksConfig":
        token = os.getenv("SPORTMONKS_API_TOKEN", "").strip()
        if not token:
            raise EnvironmentError(
                "SPORTMONKS_API_TOKEN no está configurado. "
                "Copia `.env.example` a `.env` y rellena el token."
            )
        return cls(
            api_token=token,
            base_url=os.getenv(
                "SPORTMONKS_BASE_URL",
                "https://api.sportmonks.com/v3/football",
            ),
            rate_limit_per_hour=int(os.getenv("SPORTMONKS_RATE_LIMIT_PER_HOUR", "2000")),
            league_mexico_parent=int(os.getenv("SPORTMONKS_LEAGUE_MEXICO_PARENT", "458")),
            league_liga_mx=int(os.getenv("SPORTMONKS_LEAGUE_LIGA_MX", "743")),
            league_liga_expansion=int(os.getenv("SPORTMONKS_LEAGUE_LIGA_EXPANSION", "749")),
        )


# =============================================================
# Paths del proyecto
# =============================================================

@dataclass(frozen=True)
class Paths:
    """Rutas del filesystem del proyecto."""
    project_root: Path = _PROJECT_ROOT
    data_dir: Path = _PROJECT_ROOT / "data"
    raw_dir: Path = _PROJECT_ROOT / "data" / "raw"
    processed_dir: Path = _PROJECT_ROOT / "data" / "processed"
    historical_dir: Path = _PROJECT_ROOT / "data" / "historical"
    models_dir: Path = _PROJECT_ROOT / "models"
    docs_dir: Path = _PROJECT_ROOT / "docs"
    tests_dir: Path = _PROJECT_ROOT / "tests"
    env_file: Path = _PROJECT_ROOT / ".env"


PATHS: Final[Paths] = Paths()


# =============================================================
# Base de datos
# =============================================================

DATABASE_URL: Final[str] = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{PATHS.data_dir / 'predictions_mx.db'}",
)


# =============================================================
# Logging
# =============================================================

LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE: Final[Path] = Path(os.getenv("LOG_FILE", str(PATHS.data_dir / "predictions_mx.log")))


# =============================================================
# Zona horaria
# =============================================================

TZ: Final[str] = os.getenv("TZ", "Europe/Berlin")