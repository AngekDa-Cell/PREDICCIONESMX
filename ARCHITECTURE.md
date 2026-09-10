# 🏗️ Arquitectura — Predictions_MX

Documento vivo. Se actualiza conforme el sistema crece.

**Última actualización:** 2026-09-10 (merge frontend Next.js + deploy Dokploy + sistema de quinielas)

---

## Diagrama general (septiembre 2026)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FUENTES DE DATOS EXTERNAS                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  • SportMonks v3   → fixtures, lineups, stats, events, coaches              │
│  • ESPN API        → lesiones jugadores MX (Fase 10.5)                      │
│  • Open-Meteo      → weather forecast próximos 7d                            │
│  • Odds (MVP)      → mercado sintético (cuotas reales: scraping TBD)         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTPS + rate limit 3000 calls/h
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      sportmonks_client.py                                    │
│  - Rate limiting (ventana móvil 1h)                                         │
│  - Sistema de `includes` anidados (1 por call, v3 cambió semántica 2026)    │
│  - Paginación automática                                                    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
┌────────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│  Ingesta SportMonks    │  │  Ingesta ESPN        │  │  Ingesta ODDS        │
│  (fixtures, lineups,   │  │  (lesiones MX)       │  │  (mercado MVP)       │
│   stats, coaches)      │  │                      │  │                      │
└────────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
             │                         │                         │
             └─────────────────────────┼─────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  SQLite (data/predictions_mx.db)                            │
│                  19 tablas (schema v2) — 272 MB                              │
│  fixtures, teams, seasons, players, coaches, events,                        │
│  statistics, lineups, market_odds, player_injuries,                          │
│  match_weather, analyst_predictions, ...                                     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  Feature Engineering (28 features engineered)                │
│  - Forma (exponential, recent, trend, consistency)                          │
│  - Home/away split, H2H, season context                                      │
│  - Altitud MX, rest days, fixture congestion                                │
│  - Coach tenure, referee bias, attendance ratio                              │
│  - Player injuries impact, travel distance                                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              MODELO ENSEMBLE (xg + Elo + DC + heur)                          │
│  Pesos calibrados Fase 8: xg=0.55 Elo=0.225 DC=0.135 heur=0.09              │
│  15 heurísticas validadas (derby, momentum, altitud, etc.)                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PLATT SCALING (Fase B.1) — calibración 1-vs-rest                │
│  scipy.optimize L-BFGS-B · coefs en data/platt_coefficients.json             │
│  Recalibración semanal lunes 09:00 UTC con rollback si ΔBrier >1pp          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              DECISIONES Y REPORTES                                           │
│  - BD: home_win, draw, away_win, confidence, most_likely_score               │
│  - BD: features_used (JSON con ensemble + sub-modelos + score)               │
│  - Reconciliación: outcome_hit, score_hit, bts_hit, ou_2_5_hit               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
┌────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────┐
│  Reporte diario        │  │  Frontend Next.js        │  │  Multi-agente        │
│  (Telegram bot)        │  │  predicciones.          │  │  debate (Fase 10.3)  │
│  data/daily_report.*   │  │  barberia.date           │  │  5 agentes + juez    │
│                        │  │  (Next.js 14 App Router) │  │  DWC-MAD             │
└────────────────────────┘  └────────┬─────────────────────┘  └──────────────────────┘
                                     │
                                     ▼
                     ┌────────────────────────────────┐
                     │  Sistema de quinielas         │
                     │  crowdsourced                  │
                     │  /votacion + /voto/[token]     │
                     │  + APIs /api/quiniela          │
                     │       /api/votes/[token]       │
                     │  + BD secundaria votes_mx.db   │
                     │  Cookies HttpOnly + tokens     │
                     │  base32 sha256 anti-enum       │
                     └────────────────────────────────┘
```

---

## Deploy (Dokploy, septiembre 2026)

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       DOKPLOY (panel + API)                                 │
│  predicciones.barberia.date → Traefik entrypoint websecure                  │
│                                router file-provider                         │
│                                cert wildcard *.barberia.date                │
└─────────────────────────────────┬──────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  Container Dokploy (long-running Application)                              │
│  ─────────────────────────────────────────────────────────────────────      │
│  node server.js  ← PID 1 (Next.js standalone, port :3000)                  │
│       └─ sirve frontend, /api/health, /api/quiniela, /api/votes/[token]    │
│                                                                             │
│  supercronic -no-reap /etc/crontab.app  ← PID secundario                    │
│       └─ 0 11 * * * UTC  python scripts/full_pipeline.py                    │
│       └─ 0 4  * * * UTC  bash scripts/backup_db.sh                          │
│       └─ 0 9  * * 1 UTC  bash scripts/recalibrate_platt.sh                  │
│                                                                             │
│  Bind mount: /srv/predicciones-mx/data → /workspace/proyectos/data          │
│       └─ predictions_mx.db      (RO bind para Next.js, RW para Python)     │
│       └─ votes_mx.db            (RW para Next.js, ignorado por Python)     │
│       └─ backups/, logs/        (RW para ambos)                             │
└────────────────────────────────────────────────────────────────────────────┘
```

**Ver [`docs/DEPLOY_DOKPLOY.md`](./docs/DEPLOY_DOKPLOY.md)** para procedimiento completo.  
**Ver [`deploy/DOKPLOY.md`](./deploy/DOKPLOY.md)** para guía operativa.

---

## Capas de la arquitectura

### Capa 1 — Ingesta

**4 fuentes externas** (ver [`docs/SOURCES_AUDIT.md`](./docs/SOURCES_AUDIT.md) para auditoría de cobertura):

| Fuente | Datos | Frecuencia | Cobertura |
|---|---|---|---|
| SportMonks v3 | fixtures, lineups, stats, events, coaches, venues | Diaria (11 UTC) | 100% Liga MX desde 2021 |
| ESPN API | lesiones activas | Diaria (11 UTC) | ~70-80% casos reales |
| Open-Meteo | weather próximos 7d | Diaria (11 UTC) | 93.4% próximos partidos |
| Odds MVP | cuotas sintéticas | Diaria (11 UTC) | n/a (sintético) |

**Cliente HTTP**: `src/sportmonks_client.py` — rate-limited con ventana móvil 1h, paginación automática, sistema de `includes` (1 por call, SportMonks v3 cambió semántica).

### Capa 2 — Almacenamiento

**SQLite** (`data/predictions_mx.db`) con **19 tablas SQLAlchemy 2.0** (schema v2). ~272 MB, 250K+ registros de 6 temporadas Liga MX.

**Justificación**: somos Predictions_MX + Ángel. Sin concurrencia masiva. BD = archivo portable. Migración futura trivial (cambiar `DATABASE_URL`).

**BD secundaria** (`data/votes_mx.db`) para el sistema de quinielas crowdsourced. Separada por aislamiento (writes independientes, journal_mode WAL, autocheckpoint).

**Ver [`docs/SCHEMA_V2.md`](./docs/SCHEMA_V2.md)** para detalle completo del schema.

### Capa 3 — Feature Engineering

**28 features engineered** + **15 heurísticas** validadas en literatura:

| Categoría | Features | Heurísticas |
|---|---|---|
| Forma | recent_5, exponential_form, trend, consistency, composite_momentum | streak (W/L ≥3) |
| Local/Visitante | home_away_split, h2h_winrate | — |
| Calendario | rest_days, fixture_congestion, travel_distance | fixture_congestion (>3 en 7d) |
| Plantel | coach_tenure, coach_pressure, new_manager_bounce | coach_pressure (winless ≥5) |
| Partido | referee_bias, altitude_diff, attendance_ratio | referee_adjust, altitude_MX, attendance_inverted |
| Liga | derby_flag | derby_flatten (-15%), momentum_score |

**Ver [`docs/FEATURES.md`](./docs/FEATURES.md)** para catálogo completo.

### Capa 4 — Modelos

**Ensemble de 4 modelos** (pesos calibrados Fase 8 vía grid search sobre 680 partidos 2024-2025):

```
ensemble_probs = 0.55 × xG + 0.225 × Elo + 0.135 × Dixon-Coles + 0.09 × heur
```

| Modelo individual | Accuracy | Brier | Notas |
|---|---|---|---|
| **xG proxy** (Ridge log-link) | **51.91%** | 0.6173 | Modelo individual más fuerte |
| Elo Rating (shrinkage 0.7) | 48.97% | 0.6047 | Mejor calibración individual |
| Dixon-Coles (Poisson + τ) | 41.91% | 0.6631 | Scorelines detallados |
| Heurísticas (15 reglas) | 40.74% | 0.6593 | Conocimiento del dominio |

**Experimentos NO adoptados:**
- XGBoost stacking (walk-forward 5 folds: Δ acc -0.65pp, Δ Brier -0.0031) → ensemble lineal óptimo
- A/B pesos elo-heavy (n=300: Δ acc -0.67pp) → baseline mantiene
- Isotonic regression (Platt gana en Brier en 3/3 temporadas OOS)

### Capa 5 — Calibración

**Platt scaling 1-vs-rest** (Fase B.1) — ajusta probabilidades sin cambiar el argmax:

```
P_calibrated(cls) = sigmoid(A_cls × logit(P_raw(cls)) + B_cls)
```

| Clase | A | B | Interpretación |
|---|---|---|---|
| home | 1.88 | +0.42 | Overconfianza → comprime y sube |
| draw | -0.31 | -1.43 | Overvalora draws → baja fuerte |
| away | 1.62 | +0.39 | Overconfianza → comprime y sube |

**Recalibración semanal** (lunes 09:00 UTC): build dataset 800 partidos → fit Platt → eval OOS → rollback automático si ΔBrier >1pp.

**Comparación con Isotonic** (Fase B.2, archivado): Platt gana en Brier OOS en las 3 temporadas.

### Capa 6 — Distribución

**3 destinos** de las predicciones:

1. **BD `analyst_predictions`** — para reconciliación y backtest
2. **Reporte diario** (`data/daily_report.{json,txt}`) → bot Telegram @Predictions_MX_bot
3. **Frontend Next.js** ([predicciones.barberia.date](https://predicciones.barberia.date)) — read-only bind + sistema de quinielas crowdsourced

### Capa 7 — Debate multi-agente (experimental)

Para partidos de **alta incertidumbre**, 5 sub-agentes LLM debaten en paralelo + juez DWC-MAD:

| Agente | Rol |
|---|---|
| 🐂 Bull-Local | Argumentos a favor del local |
| 🐻 Bear-Visitante | Argumentos a favor del visitante |
| 📊 Numérico | Ensemble cuantitativo (ground truth) |
| 🌐 Contextual | Noticias recientes vía web_search (lesiones, alineaciones) |
| 🔍 Data Auditor | Valida integridad de features antes de predecir |
| ⚖️ Juez | DWC-MAD (Dynamic Weighted Consensus) v2 |

**Restricción crítica (2026-06-27):** Plan MiniMax permite 3-4 agentes concurrentes. Arquitectura ajustada para ese límite.

**Permisos:** agentes NO pueden modificar VPS / BD / archivos. Solo REPORTAN bugs y aportan argumentos cualitativos.

**Resultados validación lote (n=4, 2026-06-27):** Debate 75% acc vs Numérico 50% → **+25pp**. Pendiente: Batches 3-5 para significancia estadística (n=10).

---

## Cron jobs (supercronic dentro del container Dokploy)

| Frecuencia UTC | Script | Mecanismo | Costo |
|---|---|---|---|
| `0 11 * * *` | `python scripts/full_pipeline.py` | supercronic | ~5 min + tokens LLM (multi-agente) |
| `0 4 * * *` | `bash scripts/backup_db.sh` | supercronic | ~5s, 0 tokens |
| `0 9 * * 1` | `bash scripts/recalibrate_platt.sh` | supercronic | ~45s, 0 tokens |

**Pipeline diario** (10 pasos + quick wins):
1. Ingerir lesiones ESPN
2. Refresh fixtures SportMonks (nuevos)
3. Re-ingestar lineups
4. Re-ingestar stats
5. Weather ingest próximos 7d
5b. Ingesta odds mercado (MVP)
6. Limpiar lesiones manuales
7. Regenerar predicciones (60 días, 28 features)
8. Backtest automático últimos 30 finalizados
9. Drift detection
10. Reporte completo + Telegram
- **C1b** Refresh resultados fixtures finalizados (FIX 2026-07-18)
- **C2** Reconciliación predicciones finalizadas
- **C5** Detect cambios DT

---

## Decisiones de diseño

### 1. ¿Por qué SQLite y no Postgres/MariaDB?
- **Fase actual:** somos solo nosotros (Predictions_MX + Ángel). Sin concurrencia masiva.
- **Cero infra:** la BD vive en `/workspace/proyectos/data/predictions_mx.db`. Backup = copiar archivo.
- **Portabilidad:** Ángel puede llevarse la BD a su laptop para experimentar.
- **Frontend Next.js:** usa bind mount RO del mismo SQLite. Funciona porque solo lee.
- **Migración futura:** SQLAlchemy es agnóstico. Cuando haga falta, cambiar `DATABASE_URL`.

### 2. ¿Por qué sistema de `includes` de SportMonks y no un endpoint por recurso?
- SportMonks v3 permite pedir relaciones anidadas en una sola request.
- **Caveat 2026:** SportMonks v3 cambió semántica — `include=scores,state` (comas) devuelve 404.
  Solución: una llamada por `include` (state / scores / lineups / statistics).
- Plan Custom = 3,000 calls/hora: con includes somos eficientes.

### 3. ¿Por qué rate limiting con ventana móvil de 1h?
- El límite del plan es **por hora**, no por minuto ni por día.
- Una ventana móvil (deque) nos da enforcement exacto sin importar el patrón de uso.
- Si metemos 2,000 calls en 10 minutos, esperamos ~50 minutos antes del próximo request.

### 4. ¿Por qué SQLAlchemy 2.0 con `Mapped[...]`?
- Type hints nativos (`Mapped[int]`) → mejor IDE support.
- `Mapped["Team"]` para relationships → refactor-safe.
- Misma BD si después migramos a Postgres: solo cambiar `DATABASE_URL`.

### 5. ¿Por qué ensemble lineal vs XGBoost stacking?
- Walk-forward 5 folds (Fase 10.2): XGBoost stacking dio Δ acc **-0.65pp** y Δ Brier **-0.0031**.
- Ensemble lineal sigue óptimo con dataset actual (~800 partidos).
- **Decisión:** mantener ensemble lineal. Re-evaluar en n>2000.

### 6. ¿Por qué Platt scaling 1-vs-rest y no multiclass directo?
- Más simple: 3 regresiones logísticas vs 1 softmax multinomial.
- Funciona bien con clases desbalanceadas (draw minoritario en Liga MX ~25%).
- Isotonic probado como comparación (Fase B.2): Platt gana en Brier OOS.
- Recalibrador semanal mantiene Platt fresco contra drift.

### 7. ¿Por qué crons bash puros y no OpenClaw cron?
- OpenClaw cron retryeaba en overload, gastando ~40K tokens por retry sin valor.
- Migración a supercronic dentro del container Dokploy (2026-09-09): bash puro, 0 tokens, sin retry.
- Si falla: Telegram notification + exit 1.

### 8. ¿Por qué better-sqlite3 y no Prisma en el frontend?
- **Prisma no funciona en Alpine** (libssl 1.1 incompatibilidad).
- better-sqlite3 es **nativo, rápido, read-only directo**, sin ORM intermedio.
- SQL nativo → más control sobre queries analíticas.
- Lazy init en `lib/db/client.ts` → no abre BD al import (build-time safe).

### 9. ¿Por qué cookies HttpOnly + tokens opacos en sistema de quinielas?
- **Anti-enumeración:** tokens de 8 chars base32 NO exponen `fixture_id` directo. Requieren `SECRET_SALT` para precomputar.
- **Anti-tracking:** `client_hash = sha256(cookie + ip_prefix + ua_fingerprint)[:32]`. No guardamos IPs ni UAs crudos.
- **HttpOnly + SameSite=Lax:** XSS no roba la cookie.
- **Sistema batch + individual:** mismo hash entre `/api/quiniela` y `/api/votes/[token]` → votante es el mismo.

### 10. ¿Por qué Dokploy y no VPS + nginx + certbot manual?
- **HTTPS automático** con cert wildcard `*.barberia.date` por SNI.
- **Multi-stage Dockerfile** mantiene BD bind-mount con permisos correctos.
- **Healthcheck integrado** vía `/api/health` (Next.js) → Traefik sabe cuándo restart.
- **Backup/redeploy sin downtime** Dokploy.
- **Logs centralizados** Dokploy.

### 11. ¿Por qué multi-stage Dockerfile (Node builder + Python runtime)?
- **better-sqlite3** requiere compilación nativa contra glibc → builder en Debian (no Alpine).
- **Runtime con Python 3.12** para el pipeline + supercronic.
- **Output standalone** de Next.js → `node server.js` (PID 1) sirve el front + ejecuta el pipeline.

---

## Estado actual (septiembre 2026)

✅ **Live en producción:**

- Sistema de predicciones con ensemble + Platt scaling
- Reporte diario Telegram 11:00 UTC
- Backups automáticos 04:00 UTC
- Recalibrador automático semanal lunes 09:00 UTC
- **Frontend Next.js** en [predicciones.barberia.date](https://predicciones.barberia.date) con HTTPS válido
- **Sistema de quinielas crowdsourced** (3 APIs, 2 páginas, votos + crowd summary)
- **Deploy Dokploy** con multi-stage Dockerfile + supercronic + healthcheck
- Debate multi-agente (Fase 10.3) — 5 agentes + juez DWC-MAD en partidos de alta incertidumbre

🟡 **En desarrollo:**

- Recency weighting en fit Platt (Fase B.2)
- CLV tracker (cuando odds reales)
- Drift detection automático (Fase C)

📅 **Planeado (Fase D — multimodal):**

- **Embeddings de noticias** con LLM (features textuales)
- **NLP/LLM features** integradas al ensemble
- **API robusta** con autenticación + rate limiting + monitoreo
- **CI/CD** con tests automáticos + deploy continuo a Dokploy

---

## Política de backups

- Backup diario 04:00 UTC vía `scripts/backup_db.sh` (supercronic dentro del container).
- Retención: 3 backups más recientes en `data/backups/`.
- BD bind mount con permisos `1000:1000` (user `app` en container).
- Re-deploy Dokploy preserva el bind mount → BD persiste entre deploys.

---

## Ver también

- [`docs/ARCHITECTURE_FRONTEND.md`](./docs/ARCHITECTURE_FRONTEND.md) — detalle del sistema Next.js
- [`docs/QUINIELAS_SYSTEM.md`](./docs/QUINIELAS_SYSTEM.md) — sistema de votos crowdsourced
- [`docs/DEPLOY_DOKPLOY.md`](./docs/DEPLOY_DOKPLOY.md) — procedimiento de deploy
- [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) — cómo funciona el modelo de predicción
- [`docs/ROADMAP.md`](./docs/ROADMAP.md) — roadmap completo
