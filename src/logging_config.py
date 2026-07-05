#!/usr/bin/env python3
"""
logging_config.py — Logging estructurado para Predictions_MX.

Usa logging estándar de Python con formato JSON para archivo,
y formato legible para consola.
"""

import logging
import json
import sys
from pathlib import Path
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formatter que output JSON para archivo."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            msg = record.getMessage()
            try:
                data = json.loads(msg)
            except (json.JSONDecodeError, TypeError):
                data = {"msg": msg}

            log_entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                **data,
            }

            if record.exc_text:
                log_entry["exc"] = record.exc_text

            return json.dumps(log_entry, ensure_ascii=False)
        except Exception:
            return json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "msg": record.getMessage()})


class ConsoleFormatter(logging.Formatter):
    """Formatter legible para consola con emojis."""

    LEVEL_EMOJI = {
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "DEBUG": "🔍",
        "CRITICAL": "🚨",
    }

    def format(self, record: logging.LogRecord) -> str:
        emoji = self.LEVEL_EMOJI.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        return f"{emoji} [{ts}] {record.name}: {record.getMessage()}"


def setup_pipeline_logging(
    log_file: str = None,
    level: int = logging.INFO,
    console: bool = True,
) -> logging.Logger:
    """
    Configura logging estructurado para el pipeline.

    Args:
        log_file: Path al archivo de log. Si None, no se escribe archivo.
        level: Nivel mínimo de logging.
        console: Si True, también loguea a stdout.

    Returns:
        Logger configurado.
    """
    logger = logging.getLogger("predictions_mx")
    logger.setLevel(level)
    logger.handlers.clear()

    # Archivo (JSON)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(JsonFormatter())
        logger.addHandler(fh)

    # Consola (legible)
    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(ConsoleFormatter())
        logger.addHandler(ch)

    return logger


def get_logger(name: str = "predictions_mx") -> logging.Logger:
    """Obtiene el logger del pipeline."""
    return logging.getLogger(name)


# shorthand
def log_step(step: str, status: str, **kwargs):
    """Loguea un paso del pipeline con datos estructurados."""
    logger = get_logger()
    data = {"step": step, "status": status, **kwargs}
    logger.info(json.dumps(data, ensure_ascii=False))


def log_metric(name: str, value, unit: str = ""):
    """Loguea una métrica numérica."""
    logger = get_logger()
    data = {"metric": name, "value": value}
    if unit:
        data["unit"] = unit
    logger.info(json.dumps(data, ensure_ascii=False))