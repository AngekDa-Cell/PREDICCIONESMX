"""
test_connection.py — Script de prueba para verificar el token de SportMonks.

Uso:
    python3 -m proyectos.src.test_connection
    # o desde la raíz del proyecto:
    python3 src/test_connection.py

Hace una llamada ligera a /leagues/{liga_mx_id} y muestra la respuesta.
Si falla con 401/403 → problema de token.
Si falla con 404 → el ID de la liga no existe en tu plan.
Si funciona → ✅ todo listo para empezar a ingestar.
"""

from __future__ import annotations

import json
import sys

from .config import SportMonksConfig
from .logging_setup import setup_logging
from .sportmonks_client import (
    SportMonksAuthError,
    SportMonksClient,
    SportMonksError,
    SportMonksNotFoundError,
)


def main() -> int:
    setup_logging("INFO")
    try:
        cfg = SportMonksConfig.from_env()
    except EnvironmentError as e:
        print(f"❌ {e}")
        print("\nPasos:")
        print("  1. Copia `.env.example` a `.env`")
        print("  2. Rellena SPORTMONKS_API_TOKEN con tu token")
        return 1

    print(f"🔑 Token cargado (longitud: {len(cfg.api_token)} chars)")
    print(f"🌐 Base URL: {cfg.base_url}")
    print(f"🎯 Probando con Liga MX (id={cfg.league_liga_mx})...")
    print()

    try:
        with SportMonksClient(cfg) as client:
            # 1. Ping a la liga
            league_resp = client.get_league(cfg.league_liga_mx)
            league_data = league_resp.get("data", {})
            print("✅ Conexión exitosa")
            print(f"   Liga: {league_data.get('name')!r}")
            print(f"   País: {league_data.get('country', {}).get('name') if isinstance(league_data.get('country'), dict) else league_data.get('country')}")
            print(f"   ID SportMonks: {league_data.get('id')}")
            print()

            # 2. Listar temporadas disponibles
            print("📅 Temporadas disponibles para Liga MX:")
            seasons = client.get_league_seasons(cfg.league_liga_mx)
            for s in seasons[-6:]:  # últimas 6
                start = s.get("starting_at", "")[:10] if s.get("starting_at") else "?"
                end = s.get("ending_at", "")[:10] if s.get("ending_at") else "?"
                print(f"   • {s.get('name')} ({start} → {end})  id={s.get('id')}")
            print()

            # 3. Mostrar la respuesta raw para inspección
            print("🔍 Raw response de /leagues/{id} (primeras 400 chars):")
            print(json.dumps(league_resp, indent=2, ensure_ascii=False)[:400] + "...")
            print()

            print("🎉 TODO EN ORDEN. Listo para correr los scripts de ingesta.")
            return 0

    except SportMonksAuthError as e:
        print(f"❌ Auth fallida: {e}")
        print("   → Verifica que el token esté bien copiado en .env")
        return 2
    except SportMonksNotFoundError as e:
        print(f"❌ Liga no encontrada: {e}")
        print(f"   → El ID {cfg.league_liga_mx} no existe o no está en tu plan")
        return 3
    except SportMonksError as e:
        print(f"❌ Error de SportMonks: {e}")
        return 4
    except Exception as e:
        print(f"💥 Error inesperado: {type(e).__name__}: {e}")
        return 99


if __name__ == "__main__":
    sys.exit(main())