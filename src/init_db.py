"""
init_db.py — Crea todas las tablas en la BD SQLite.

Uso:
    python3 src/init_db.py
"""

from __future__ import annotations

import sys

from .db import init_db


if __name__ == "__main__":
    init_db()
    sys.exit(0)