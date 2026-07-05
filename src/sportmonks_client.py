"""
sportmonks_client.py — Cliente HTTP para la API v3 de SportMonks.

Características:
- Autenticación por query param `api_token`.
- Rate limiting respetando el límite del plan (tokens por hora).
- Retries con backoff exponencial para errores transitorios.
- Soporte del sistema de `includes` (anida relaciones en una sola request).
- Logging estructurado de cada request.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

import requests
from requests.exceptions import HTTPError, RequestException, Timeout

from .config import SportMonksConfig


def _extract_cursor(url_or_cursor: str) -> str | None:
    """Extrae el parámetro `cursor` de una URL completa de next_cursor.
    
    SportMonks devuelve next_cursor como URL completa:
        https://api.sportmonks.com/v3/football/fixtures?...&cursor=XXXXX
    Necesitamos solo el valor del parámetro `cursor`.
    """
    if not url_or_cursor:
        return None
    # Si ya parece un cursor opaco (no es URL), devolverlo tal cual
    if not url_or_cursor.startswith("http"):
        return url_or_cursor
    try:
        parsed = urlparse(url_or_cursor)
        qs = parse_qs(parsed.query)
        cursor_list = qs.get("cursor")
        if cursor_list:
            return cursor_list[0]
    except Exception:
        return None
    return None

logger = logging.getLogger(__name__)


# =============================================================
# Excepciones del cliente
# =============================================================

class SportMonksError(Exception):
    """Error base del cliente SportMonks."""


class SportMonksAuthError(SportMonksError):
    """Token inválido, expirado o sin permisos para el recurso."""


class SportMonksRateLimitError(SportMonksError):
    """Rate limit excedido (HTTP 429)."""


class SportMonksNotFoundError(SportMonksError):
    """Recurso no encontrado (HTTP 404)."""


# =============================================================
# Cliente principal
# =============================================================

class SportMonksClient:
    """
    Cliente de la API v3 de SportMonks para fútbol.

    Implementa:
    - Rate limiting con ventana móvil de 1 hora.
    - Retries automáticos con backoff exponencial.
    - Helpers para endpoints comunes (leagues, seasons, teams, fixtures).
    """

    DEFAULT_TIMEOUT: int = 30  # segundos
    MAX_RETRIES: int = 4
    BACKOFF_BASE: float = 1.5  # segundos

    def __init__(self, config: SportMonksConfig) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.params = {"api_token": config.api_token}
        # Ventana móvil de timestamps de requests para rate limiting
        self._request_timestamps: deque[float] = deque(maxlen=config.rate_limit_per_hour)
        logger.info(
            "SportMonksClient inicializado | rate_limit=%d/h",
            config.rate_limit_per_hour,
        )

    # ---------------------------------------------------------
    # Rate limiting
    # ---------------------------------------------------------

    def _throttle(self) -> None:
        """Bloquea hasta que haya hueco en la ventana de rate limit."""
        now = time.monotonic()
        window_start = now - 3600  # 1 hora
        # Descartar timestamps fuera de la ventana
        while self._request_timestamps and self._request_timestamps[0] < window_start:
            self._request_timestamps.popleft()
        if len(self._request_timestamps) >= self.config.rate_limit_per_hour:
            sleep_for = 3600 - (now - self._request_timestamps[0]) + 0.5
            logger.warning(
                "Rate limit alcanzado (%d/%d). Durmiendo %.1fs...",
                len(self._request_timestamps),
                self.config.rate_limit_per_hour,
                sleep_for,
            )
            time.sleep(sleep_for)
        self._request_timestamps.append(time.monotonic())

    # ---------------------------------------------------------
    # Core: request genérico
    # ---------------------------------------------------------

    def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        _retries: int = 0,
    ) -> dict[str, Any]:
        """
        Ejecuta un GET contra la API con retries y manejo de errores.
        """
        self._throttle()
        url = f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        query_params = dict(self._session.params)  # api_token
        if params:
            query_params.update(params)

        try:
            logger.debug("GET %s | params=%s", endpoint, {k: v for k, v in query_params.items() if k != "api_token"})
            resp = self._session.get(url, params=query_params, timeout=self.DEFAULT_TIMEOUT)
        except Timeout as e:
            return self._retry_or_raise(endpoint, params, _retries, f"timeout: {e}")
        except RequestException as e:
            return self._retry_or_raise(endpoint, params, _retries, f"network error: {e}")

        # Manejo por status code
        if resp.status_code == 401 or resp.status_code == 403:
            raise SportMonksAuthError(
                f"Auth fallida ({resp.status_code}). Token inválido o sin permisos."
            )
        if resp.status_code == 404:
            raise SportMonksNotFoundError(f"Recurso no encontrado: {endpoint}")
        if resp.status_code == 429:
            if _retries < self.MAX_RETRIES:
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning("HTTP 429 rate-limited. Esperando %ds...", wait)
                time.sleep(wait)
                return self._request(endpoint, params, _retries + 1)
            raise SportMonksRateLimitError("Rate limit agotado tras varios retries.")
        if resp.status_code >= 500:
            return self._retry_or_raise(
                endpoint, params, _retries,
                f"server error {resp.status_code}",
            )

        try:
            resp.raise_for_status()
        except HTTPError as e:
            raise SportMonksError(f"HTTP error {resp.status_code}: {resp.text}") from e

        try:
            payload = resp.json()
        except ValueError as e:
            raise SportMonksError(f"Respuesta no es JSON válido: {e}") from e

        # La API envuelve las respuestas en {"data": ..., "pagination": ...}
        if isinstance(payload, dict) and "data" in payload:
            return payload
        return {"data": payload}

    def _retry_or_raise(
        self,
        endpoint: str,
        params: dict[str, Any] | None,
        retries: int,
        reason: str,
    ) -> dict[str, Any]:
        if retries < self.MAX_RETRIES:
            wait = self.BACKOFF_BASE ** (retries + 1)
            logger.warning(
                "%s en %s. Retry %d/%d en %.1fs...",
                reason, endpoint, retries + 1, self.MAX_RETRIES, wait,
            )
            time.sleep(wait)
            return self._request(endpoint, params, retries + 1)
        raise SportMonksError(f"{reason} en {endpoint} tras {self.MAX_RETRIES} retries.")

    # ---------------------------------------------------------
    # Helpers para paginación
    # ---------------------------------------------------------

    def _iter_pages(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        per_page: int = 50,
    ) -> Iterable[dict[str, Any]]:
        """Itera sobre todas las páginas de un endpoint.
        
        SportMonks v3 usa paginación por CURSOR (no por página). Si el API
        devuelve `next_cursor`, lo seguimos. Si no, usamos `page=N` como
        fallback. Tenemos un safety limit de MAX_PAGES para evitar loops.
        """
        MAX_PAGES = 100  # safety: 100 * 50 = 5000 items max por iteración
        cursor: str | None = None
        page = 1

        for _ in range(MAX_PAGES):
            merged = dict(params or {})
            if cursor is not None:
                # Cuando usamos cursor, NO mandamos per_page NI page
                merged["cursor"] = cursor
                merged.pop("per_page", None)
                merged.pop("page", None)
            else:
                merged["per_page"] = per_page
                merged["page"] = page

            payload = self._request(endpoint, merged)
            data = payload.get("data", [])
            if not data:
                break
            for item in data:
                yield item

            pagination = payload.get("pagination", {}) or {}
            next_cursor_raw = pagination.get("next_cursor")
            count = pagination.get("count", 0)
            has_more = pagination.get("has_more")

            # Si el API da next_cursor, extraer el parámetro 'cursor=' de la URL
            if next_cursor_raw:
                cursor = _extract_cursor(next_cursor_raw)
                if not cursor:
                    # No se pudo extraer → terminamos
                    break
                continue
            # Si no hay next_cursor pero count < per_page, última página
            if count and count < per_page:
                break
            # Si has_more=False explícito, terminamos
            if has_more is False:
                break
            # Fallback: incrementar page
            page += 1

    def get_all(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Devuelve todos los items de un endpoint (todas las páginas)."""
        return list(self._iter_pages(endpoint, params))

    # ---------------------------------------------------------
    # Helpers de includes
    # ---------------------------------------------------------

    @staticmethod
    def include(*parts: str) -> str:
        """Une partes de un include en formato SportMonks: 'a.b.c'."""
        return ";".join(parts)

    # ---------------------------------------------------------
    # Endpoints de alto nivel (los que más vamos a usar)
    # ---------------------------------------------------------

    def get_league(self, league_id: int, include: str | None = None) -> dict[str, Any]:
        """GET /leagues/{id}"""
        params = {"include": include} if include else None
        return self._request(f"leagues/{league_id}", params)

    def get_league_seasons(self, league_id: int) -> list[dict[str, Any]]:
        """GET /leagues/{id}?include=seasons — todas las temporadas de la liga.
        
        En SportMonks v3 las temporadas vienen como relación anidada de la liga
        (no como sub-endpoint). Si el endpoint plano /leagues/{id}/seasons
        devuelve 404, usar este método.
        """
        resp = self._request(f"leagues/{league_id}", {"include": "seasons"})
        data = resp.get("data", {})
        return data.get("seasons", []) or []

    def get_season(self, season_id: int, include: str | None = None) -> dict[str, Any]:
        """GET /seasons/{id}"""
        params = {"include": include} if include else None
        return self._request(f"seasons/{season_id}", params)

    def get_season_teams(
        self,
        season_id: int,
        include: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /seasons/{id}?include=teams — equipos de una temporada.
        
        En SportMonks v3 los equipos vienen como include, no como sub-endpoint.
        Si /seasons/{id}/teams devuelve 404, usar este método.
        """
        params = {"include": "teams"} if include is None else {"include": include}
        resp = self._request(f"seasons/{season_id}", params)
        data = resp.get("data", {})
        return data.get("teams", []) or []

    def get_fixtures_by_season(
        self,
        season_id: int,
        include: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /seasons/{id}?include=fixtures[.subincludes] — fixtures de una temporada.
        
        Esta es la forma más eficiente: una sola llamada trae TODOS los fixtures
        de la temporada con los sub-includes anidados que se pidan.
        Sintaxis de includes anidados: 'fixtures.participants;fixtures.scores;...'
        Si no se pasan sub-includes, devuelve solo los fixtures básicos.
        """
        if include:
            # prepend 'fixtures.' a cada parte del include
            sub_includes = include.replace(" ", "").split(";")
            nested = ";".join(f"fixtures.{s}" for s in sub_includes if s)
            return self._request(f"seasons/{season_id}", {
                "include": nested,
            }).get("data", {}).get("fixtures", []) or []
        # Sin sub-includes: igual eficiente
        return self._request(f"seasons/{season_id}", {
            "include": "fixtures",
        }).get("data", {}).get("fixtures", []) or []

    def get_fixture(self, fixture_id: int, include: str | None = None) -> dict[str, Any]:
        """GET /fixtures/{id}"""
        params = {"include": include} if include else None
        return self._request(f"fixtures/{fixture_id}", params)

    def get_team(self, team_id: int, include: str | None = None) -> dict[str, Any]:
        """GET /teams/{id}"""
        params = {"include": include} if include else None
        return self._request(f"teams/{team_id}", params)

    def get_team_squad(self, season_id: int, team_id: int) -> list[dict[str, Any]]:
        """GET /squads/season/{season_id}/team/{team_id}"""
        return self.get_all(f"squads/season/{season_id}/team/{team_id}")

    def get_player(self, player_id: int) -> dict[str, Any]:
        """GET /players/{id}"""
        return self._request(f"players/{player_id}")

    def get_standings_by_season(self, season_id: int) -> list[dict[str, Any]]:
        """GET /standings/seasons/{id}"""
        return self.get_all(f"standings/seasons/{season_id}")

    def get_livescores(self, league_ids: list[int] | None = None) -> list[dict[str, Any]]:
        """GET /livescores (o /livescores/inplay)."""
        params = {}
        if league_ids:
            params["filters"] = "leagueId:" + ";".join(str(i) for i in league_ids)
        return self.get_all("livescores/inplay", params)

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        self._session.close()
        logger.info("SportMonksClient cerrado.")

    def __enter__(self) -> "SportMonksClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()