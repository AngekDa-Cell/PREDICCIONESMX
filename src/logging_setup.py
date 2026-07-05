"""
logging_setup.py — Configuración centralizada de logging.

Log a consola (stderr) + a archivo rotativo en data/predictions_mx.log.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOG_FILE, LOG_LEVEL


def setup_logging(level: str | None = None) -> None:
    """Configura el logging global del paquete."""
    log_level = (level or LOG_LEVEL).upper()
    log_file = LOG_FILE
    log_file.parent.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # Consola
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    # Archivo (rotativo, 5 MB x 3 backups)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    # Evitar handlers duplicados si se llama varias veces
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)
    root.setLevel(log_level)

    # Silenciar librerías ruidosas
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)