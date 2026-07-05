# 🏗️ Arquitectura — Predictions_MX

Documento vivo. Se actualiza conforme el sistema crece.

---

## Diagrama general

```
┌─────────────────────────────────────────────────────────────────┐
│                       SPORTMONKS API v3                          │
│  https://api.sportmonks.com/v3/football                          │
│  - 2300+ ligas, 15+ años histórico                              │
│  - Endpoints: leagues, seasons, fixtures, teams, players...     │
│  - Sistema de "includes" para relaciones anidadas               │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS + api_token (query)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  sportmonks_client.py                            │
│  - Rate limiting (ventana móvil 1h, configurable por plan)       │
│  - Retries con backoff exponencial                               │
│  - Paginación automática                                         │
│  - Helpers de alto nivel (get_league, get_fixtures_by_season)   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│            Scripts de ingesta (src/ingest_*.py)                  │
│  - ingest_leagues.py → Liga MX, Liga Expansión                  │
│  - ingest_seasons.py → Apertura/Clausura 2020-2026              │
│  - ingest_teams.py   → 20 equipos Liga MX                       │
│  - ingest_fixtures.py → todos los partidos                      │
│  - ingest_events.py  → goles, tarjetas, sustituciones           │
│  - ingest_stats.py   → posesión, tiros, córners, etc.            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQLite (data/predictions_mx.db)            │
│  Tablas:                                                         │
│    leagues, seasons, teams, venues, players,                    │
│    fixtures, fixture_events, fixture_statistics, ...            │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
   ┌─────────────────────┐       ┌─────────────────────────┐
   │ Feature engineering │       │ Modelos ML              │
   │ (pandas/numpy)      │       │ - Poisson bivariado     │
   │ - Forma reciente    │       │ - Dixon-Coles           │
   │ - H2H               │       │ - XGBoost / LightGBM    │
   │ - Local/visitante   │       │ - Ensemble              │
   │ - xG (si add-on)    │       └────────────┬────────────┘
   └──────────┬──────────┘                    │
              │                               │
              └─────────────┬─────────────────┘
                            ▼
              ┌──────────────────────────────┐
              │   Sistema de predicción       │
              │   - Probabilidad 1X2         │
              │   - Goles esperados           │
              │   - Confianza (%)             │
              │   - Razón principal           │
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  Reportes / Telegram Bot      │
              │  (este chat con @angelpadilla)│
              └──────────────────────────────┘
```

---

## Decisiones de diseño

### 1. ¿Por qué SQLite y no Postgres/MariaDB?
- **Fase actual:** somos solo nosotros (Predictions_MX + Ángel). No hay concurrencia masiva.
- **Cero infra:** la BD vive en `/workspace/proyectos/data/predictions_mx.db`. Backup = copiar el archivo.
- **Portabilidad:** Ángel puede llevarse la BD a su laptop para experimentar.
- **Migración futura:** SQLAlchemy es agnóstico. Cuando haga falta, cambiamos `DATABASE_URL` y boom, Postgres.

### 2. ¿Por qué sistema de `includes` de SportMonks y no un endpoint por recurso?
- SportMonks permite pedir relaciones anidadas en una sola request:
  `GET /fixtures?include=events;lineups;statistics;participants`
- Esto reduce drásticamente el número de calls necesarias.
- Plan Starter = 2,000 calls/hora: con includes somos mucho más eficientes.

### 3. ¿Por qué rate limiting con ventana móvil de 1h y no algo más simple?
- El límite del plan es **por hora**, no por minuto ni por día.
- Una ventana móvil (deque) nos da enforcement exacto sin importar el patrón de uso.
- Si metemos 2,000 calls en 10 minutos, esperamos ~50 minutos antes del próximo request.

### 4. ¿Por qué SQLAlchemy 2.0 con `Mapped[...]` y no Core crudo?
- Type hints nativos (`Mapped[int]`) → mejor IDE support.
- `Mapped["Team"]` para relationships → refactor-safe.
- Misma BD si después migramos a Postgres: solo cambiar `DATABASE_URL`.

---

## Estado actual (junio 2026)

✅ **Listo:**
- Estructura del proyecto
- Cliente SportMonks con rate-limiting y retries
- Modelos SQLAlchemy
- Scripts de ingesta de ligas y temporadas
- Script de prueba de conexión

⏳ **Pendiente:**
- Esperar token de Ángel para correr `test_connection.py`
- Crear `ingest_teams.py`, `ingest_fixtures.py`, `ingest_events.py`, `ingest_stats.py`
- Backfill histórico (3+ temporadas)
- Feature engineering
- Modelos ML

---

## Política de backups

Por ahora la BD está en `/workspace/proyectos/data/predictions_mx.db`. Pendiente:
- Backup diario a `/workspace/proyectos/data/historical/`
- Snapshot antes de cada actualización masiva

(Cuando el sistema esté en producción, podemos mover la BD a MariaDB en un container aparte.)