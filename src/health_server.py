#!/usr/bin/env python3
"""
health_server.py — HTTP healthcheck endpoint para Dokploy / Traefik / monitoring.

Sirve en :HEALTH_PORT (default 8080). Endpoints:
- GET /health       → 200 JSON {status:"ok", service, uptime_seconds}
- GET /             → 200 JSON (alias)
- GET /version      → 200 JSON {git_sha, started_at}
- cualquier otro    → 404

Uso (background dentro del container, junto a supercronic):
    python3 -m src.health_server
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("HEALTH_PORT", "8080"))
SERVICE = os.getenv("HEALTH_SERVICE_NAME", "predicciones-mx")
GIT_SHA = os.getenv("GIT_SHA", "unknown")
START_TIME = time.time()


class HealthHandler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path in ("/health", "/", "/healthz"):
            return self._json(200, {
                "status": "ok",
                "service": SERVICE,
                "uptime_seconds": int(time.time() - START_TIME),
            })
        if self.path == "/version":
            return self._json(200, {
                "service": SERVICE,
                "git_sha": GIT_SHA,
                "started_at": int(START_TIME),
            })
        return self._json(404, {"status": "not_found", "path": self.path})

    def log_message(self, fmt, *args) -> None:  # noqa: A003
        # silenciar logs por defecto; supercronic ya hace el ruido del cron
        return


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"🏥 Healthcheck server listening on :{PORT} (service={SERVICE})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
