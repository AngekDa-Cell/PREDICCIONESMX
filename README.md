# ⚽ Predictions_MX — Sistema Profesional de Predicciones Liga MX

> **Web pública:** [predicciones.barberia.date](https://predicciones.barberia.date) · **Bot:** [@Predictions_MX_bot](https://t.me/Predictions_MX_bot) · **Owner:** Ángel Padilla · **Última actualización:** 2026-09-10

Sistema **full-stack** de predicciones para la **Liga MX**: backend Python (predicción + calibración + debate multi-agente) + frontend Next.js (visualización + sistema de quinielas crowdsourced). Pipeline automatizado de ingesta → predicción → publicación → distribución (Telegram + web).

---

## 🎯 ¿Qué es esto?

**Sistema completo en este repo** (antes el frontend vivía separado, ahora está integrado):

1. **Backend de predicción** (`src/`, `scripts/`) — ingesta SportMonks + ESPN + Open-Meteo, modelo ensemble, calibración Platt, debate multi-agente, reportes Telegram.
2. **Frontend Next.js** (`app/`, `components/`, `lib/`) — visualización pública + sistema de quinielas crowdsourced (votación de la comunidad, cookies HttpOnly, validación anti-SQLi).

**Objetivo:** predecir resultados de Liga MX con **accuracy OOS >50%** (baseline aleatorio 33%, estado del arte ≈55-60%) usando 28 features engineered, ensemble de 4 modelos calibrados, debate multi-agente y dashboard público con auditoría completa.

---

## ⚡ Quick Start

### Backend (pipeline diario)

```bash
# Variables de entorno (Ángel tiene los tokens)
cp .env.example .env
# Editar .env con SPORTMONKS_API_TOKEN, TELEGRAM_BOT_TOKEN

# Dependencias (Python 3.12)
pip3 install --break-system-packages -r requirements.txt

# Pipeline diario (corre automático vía supercronic 11:00 UTC dentro del container Dokploy)
python3 scripts/full_pipeline.py

# Predicción ad-hoc (próximos partidos)
python3 src/predict/cli.py --home "América" --away "Chivas"
```

### Frontend (Next.js)

```bash
cd /workspace/proyectos
npm install
npm run dev        # dev server :3000
npm run build      # build standalone para Dokploy
```

### Dependencias completas

**Backend Python** (`requirements.txt`, pinned 2026-09-09):
- `requests`, `pandas`, `numpy`, `sqlalchemy>=2.0`
- `scipy`, `scikit-learn`, `xgboost`
- `python-dotenv`

**Frontend TypeScript** (`package.json`):
- Next.js 14.2.5, React 18.3, TypeScript 5.5
- Tailwind 3.4, lucide-react, Recharts 2.13
- better-sqlite3 12.11 (BD read-only nativa)

---

## 📊 Estado actual (septiembre 2026)

### Métricas live (Fase B.1 con Platt scaling)

| Métrica | Pre Platt | **Post Platt** | Δ vs baseline |
|---|---|---|---|
| **Accuracy OOS** (n=994, 3 temp) | 50.6% | **51.1%** | +17.8pp vs 33.3% random |
| **Brier Score /3** | 0.2042 | **0.2009** | -0.33pp |
| **Log Loss** | 1.0203 | **1.0158** | -0.0045 |

Calibración excelente por tier:
- High (60-70%, n=7): 85.7% acc
- Medium (50-60%, n=8): 50% acc
- Low (<50%, n=38): 39.5% acc (random)

### Modelo ensemble (Fase 8 — pesos calibrados)

- **xG proxy** (Ridge log-link, decay 0.85): **55%**
- **Elo Rating** (shrinkage 0.7): **22.5%**
- **Dixon-Coles** (Poisson + τ): **13.5%**
- **15 heurísticas**: **9%**

→ Ver [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) para detalle técnico completo.

### Debate multi-agente (Fase 10.3, experimental)

5 sub-agentes LLM en paralelo para partidos de alta incertidumbre:
- 🐂 Bull-Local · 🐻 Bear-Visitante · 📊 Numérico (ensemble) · 🌐 Contextual (web_search) · 🔍 Data Auditor
- ⚖️ Juez DWC-MAD (Dynamic Weighted Consensus)
- **Validación lote (n=4)**: Debate 75% acc vs Numérico 50% → **+25pp**

→ Ver [`docs/ROADMAP.md`](./docs/ROADMAP.md#fase-10-multi-agente) sección Fase 10.

---

## 🏗️ Arquitectura (high-level)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FUENTES DE DATOS EXTERNAS                         │
├─────────────────────────────────────────────────────────────────────┤
│  SportMonks v3   →  fixtures, lineups, stats, events, coaches        │
│  ESPN API        →  lesiones activas Liga MX (Fase 10.5)            │
│  Open-Meteo      →  weather forecast próximos 7d                     │
│  Odds (MVP)      →  mercado sintético (cuotas reales: scraping TBD) │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │ HTTPS + rate limit 3000 calls/h
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│              sportmonks_client.py (rate-limited, includes)          │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────────┐      ┌─────────────────┐
│ Ingesta SM      │      │ Ingesta ESPN        │      │ Ingesta ODDS    │
│ (fixtures,      │      │ (lesiones MX)       │      │ (mercado MVP)   │
│  lineups, stats)│      │                     │      │                 │
└────────┬────────┘      └─────────┬───────────┘      └────────┬────────┘
         │                         │                           │
         └─────────────────────────┼───────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│        SQLite (data/predictions_mx.db) — schema v2 — 272 MB         │
│        19 tablas SQLAlchemy 2.0 · 250K+ registros Liga MX           │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Feature Engineering (28 features)                  │
│  Forma (exp/recent/trend/consistency) · Home/away split · H2H        │
│  Altitud MX · Rest days · Fixture congestion · Coach tenure         │
│  Referee bias · Attendance ratio · Player injuries · Travel dist.   │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│             ENSEMBLE (xg=0.55 + Elo=0.225 + DC=0.135 + heur=0.09)   │
│             15 heurísticas validadas (derby, momentum, altitud...)   │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PLATT SCALING 1-vs-rest (Fase B.1) — calibración       │
│              scipy.optimize L-BFGS-B · coefs data/platt_coefficients│
│              Recalibración semanal lunes 09:00 UTC + rollback auto  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│       DECISIONES Y REPORTES                                        │
│       BD: 1X2 + confidence + most_likely_score + features_used      │
│       Reconciliación: outcome_hit + score_hit + bts_hit + ou_2_5    │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
┌────────────────────┐  ┌──────────────────────┐  ┌─────────────────┐
│ Reporte diario     │  │ Frontend Next.js     │  │ Multi-agente    │
│ Telegram bot       │  │ predicciones.       │  │ debate (Fase    │
│ data/daily_report  │  │ barberia.date       │  │ 10.3)           │
└────────────────────┘  └──────────────────────┘  └─────────────────┘
                                   │
                                   ▼
                       ┌──────────────────────┐
                       │ Sistema quinielas    │
                       │ crowdsourced         │
                       │ /votacion + /voto/   │
                       │ [token]              │
                       │ Cookies HttpOnly     │
                       │ Validación anti-SQLi │
                       └──────────────────────┘
```

**Ver [`ARCHITECTURE.md`](./ARCHITECTURE.md)** para detalle de decisiones + diagramas por capa.  
**Ver [`docs/ARCHITECTURE_FRONTEND.md`](./docs/ARCHITECTURE_FRONTEND.md)** para detalle del frontend Next.js.  
**Ver [`docs/QUINIELAS_SYSTEM.md`](./docs/QUINIELAS_SYSTEM.md)** para el sistema de votos.

---

## 📋 Tablas BD (SQLite: `data/predictions_mx.db`)

| Tabla | Registros | Fuente | Notas |
|---|---:|---|---|
| `fixtures` | 3,143 | SportMonks | Partidos, scores, attendance |
| `seasons` | 44 | SportMonks | Temporadas Liga MX |
| `teams` | 47 | SportMonks | Equipos + colores + venue |
| `venues` | 45 | SportMonks + manual | Con altitud calibrada |
| `players` | 2,492 | SportMonks | Jugadores |
| `coaches` | 285 | SportMonks | DTs |
| `coach_tenures` | 1,082 | SportMonks | Historial DT |
| `fixture_events` | 53,770 | SportMonks | Goles, tarjetas, cambios |
| `fixture_statistics` | 192,370 | SportMonks | Tiros, posesión, etc. |
| `fixture_lineups` | 127,186 | SportMonks | Alineaciones |
| `analyst_predictions` | live + backtest | Calculado | Predicciones ensemble |
| `market_odds` | 14d rolling | MVP sintético | Pendiente cuotas reales |
| `player_injuries` | activo | ESPN API (Fase 10.5) | Cobertura ~70-80% |
| `match_weather` | próximos 7d | Open-Meteo | Cobertura 93.4% |
| `votes` (BD secundaria) | live | Web | BD `votes_mx.db` RW |
| `vote_meta` (BD secundaria) | live | Web | Counter + first/last |

**Ligas:** Liga MX (id=743) — 6 temporadas scrapeadas (2021-2027 parcial).

---

## 🗺️ Roadmap

### ✅ Completado

- **Fase 1-5**: Schema, ingesta, modelos base, calibración, backtesting (2026)
- **Fase 6-9**: Recalibración Platt, threshold mínimo, attendance heur, referee bias, weather ingest, xG proxy
- **Fase 10.1-10.3**: Sistema multi-agente debate (Bull/Bear/Numérico/Contextual/Auditor + Juez DWC-MAD)
- **Fase A**: Frontend Next.js LIVE (predicciones.barberia.date), sistema de votos Sprint 4 completo, market odds MVP
- **Fase B.1**: Platt scaling en producción, recalibrador automático semanal (jul 2026)
- **Fase C0-C1**: Deploy Dokploy + healthcheck HTTP + Traefik + multi-stage Dockerfile (sep 2026)
- **Fix**: paso C1b refresh fixtures resultados (jul 2026)

### 🔄 En progreso (Fase B.2)

- Recency weighting en fit Platt (drift temporal)
- CLV tracker (cuando odds reales disponibles)

### 📅 Planeado (Fase D — multimodal)

- **Embeddings de noticias**: features textuales con LLM para partidos de alta incertidumbre
- **NLP/LLM features**: integrar contexto (lesiones reportadas, declaraciones DT) en el ensemble
- **API robusta**: endpoints con autenticación + rate limiting + monitoreo
- **CI/CD**: pipeline de tests automático + deploy continuo a Dokploy

Ver [`docs/ROADMAP.md`](./docs/ROADMAP.md) para detalle completo.

---

## 📁 Estructura del proyecto

```
PREDICCIONESMX/
├── src/                                # Backend Python
│   ├── config.py                       # Config desde .env
│   ├── sportmonks_client.py            # Cliente HTTP rate-limited
│   ├── db.py                           # 19 modelos SQLAlchemy (schema v2)
│   ├── health_server.py                # /health endpoint (legacy, ahora Next.js)
│   ├── ingest_*.py                     # Scripts de ingesta (SportMonks, ESPN, weather, odds)
│   ├── predict/                        # Sistema de predicción
│   │   ├── features.py                 # 28 features engineered
│   │   ├── elo.py                      # Elo rating (FiveThirtyEight style)
│   │   ├── dixon_coles.py              # Poisson + τ
│   │   ├── xg.py                       # xG proxy (Ridge log-link)
│   │   ├── heuristics.py               # 15 heurísticas
│   │   ├── backtest.py                 # Validación OOS
│   │   ├── calibration.py              # Platt scaling (Fase B.1)
│   │   └── ...
│   └── agents/                         # Multi-agente debate (Fase 10)
│       ├── orchestrator.py             # Orquestador 3 agentes + juez
│       ├── orchestrator_live.py        # Orquestador con LLM real
│       ├── judge.py                    # DWC-MAD v2
│       ├── contextual.py               # Agente noticias (web_search)
│       ├── data_auditor.py             # Validador integridad
│       └── prompts.py                  # Templates de prompts
│
├── scripts/                            # Operación
│   ├── full_pipeline.py                # Pipeline diario (10 pasos + quick wins)
│   ├── reconcile_outcomes.py           # Pred vs realidad
│   ├── refresh_fixtures_results.py     # C1b: refresh resultados
│   ├── recalibrate_platt.sh            # Recalibrador semanal
│   ├── backup_db.sh                    # Backup diario (cron 04 UTC)
│   └── ...
│
├── app/                                # Frontend Next.js (App Router)
│   ├── page.tsx                        # Home (dashboard Cinépolis-style)
│   ├── layout.tsx                      # Layout raíz + TopNav
│   ├── globals.css                     # iOS-style design system
│   ├── analisis/page.tsx               # Análisis agregado
│   ├── calendario/page.tsx             # Calendario por jornada
│   ├── efectividad/page.tsx            # Métricas efectividad
│   ├── equipos/page.tsx                # Índice de equipos
│   ├── equipo/[id]/page.tsx            # Detalle de equipo
│   ├── historial/page.tsx              # Historial de predicciones
│   ├── partido/[id]/page.tsx           # Detalle de partido
│   ├── resultados/page.tsx             # Track record
│   ├── votacion/page.tsx               # Llenar quiniela batch
│   ├── voto/[token]/page.tsx           # Voto individual partido
│   └── api/                            # API routes (3 endpoints)
│       ├── health/route.ts             # Healthcheck Traefik
│       ├── quiniela/route.ts           # POST batch + GET picks
│       └── votes/[token]/route.ts      # POST/GET voto individual
│
├── components/                         # Componentes React
│   ├── ui/                             # TeamCrest, ProbabilityBars, etc.
│   ├── layout/                         # Navigation, PageHeader, BackButton
│   ├── fixtures/                       # FixtureRow, FixtureDetail, MatchClock, PickBadge
│   ├── stats/                          # StatsBadge
│   └── votes/                          # QuinielaForm, VoteForm, CrowdSummary
│
├── lib/                                # Lógica frontend
│   ├── db/                             # SQLite read-only (client.ts)
│   │   ├── client.ts                   # Singleton BD principal (lazy)
│   │   ├── votes-client.ts             # Singleton BD votos (lazy, RW)
│   │   ├── types.ts                    # Types TypeScript
│   │   ├── fixtures.ts                 # Queries fixtures
│   │   ├── predictions.ts              # Queries predicciones
│   │   ├── teams.ts                    # Queries equipos
│   │   ├── matchday.ts                 # Lógica de jornadas
│   │   ├── stats.ts                    # Stats agregadas (Brier, accuracy)
│   │   └── votes.ts                    # Sistema de votos
│   ├── votes/                          # Helpers de votación
│   │   ├── client-hash.ts              # Fingerprint votante (cookie+IP+UA)
│   │   └── token.ts                    # Tokens de 8 chars base32
│   ├── validation.ts                   # Regex anti-SQLi + sanitize
│   └── db.ts (re-exports)
│
├── tests/                              # 257 tests Python (~30s)
│   ├── conftest.py
│   ├── test_backtest.py
│   ├── test_dixon_coles.py
│   ├── test_elo.py
│   ├── test_ensemble.py
│   ├── test_features.py
│   ├── test_heuristics.py
│   ├── test_xg.py
│   ├── test_injuries_impact.py
│   ├── test_integration.py
│   ├── test_multi_agent.py
│   ├── test_orchestrator_live.py
│   ├── test_recalibration.py
│   ├── test_referee_bias.py
│   ├── test_shrinkage.py
│   ├── test_stacking.py
│   ├── test_threshold.py
│   ├── test_weather.py
│   └── ...
│
├── data/                               # Datos runtime
│   ├── predictions_mx.db               # BD principal (~272 MB)
│   ├── votes_mx.db                     # BD de votos (RW)
│   ├── platt_coefficients.json         # Coefs Platt actuales
│   ├── mx_coefficients.json            # Pesos ensemble + shrinkage
│   ├── daily_report.{json,txt}         # Reporte diario (Telegram-ready)
│   ├── multi_agent_*.json              # Logs de debates multi-agente
│   ├── backtest_*.json                 # Resultados de backtests
│   ├── backups/                        # Últimos 3 backups BD
│   └── logs/                           # Logs estructurados
│
├── docs/                               # Documentación
│   ├── ROADMAP.md                      # Roadmap completo
│   ├── METHODOLOGY.md                  # Cómo funciona el modelo
│   ├── BACKTESTING_RESULTS.md          # Métricas empíricas
│   ├── FEATURES.md                     # Catálogo de 28 features
│   ├── SCHEMA_V2.md                    # Diseño BD
│   ├── RESEARCH_SYNTHESIS.md           # Papers revisados
│   ├── ARTICLES_INVENTORY.md           # Inventario bibliográfico
│   ├── SOURCES_AUDIT.md                # Auditoría de fuentes
│   ├── ARCHITECTURE_FRONTEND.md        # Sistema Next.js
│   ├── QUINIELAS_SYSTEM.md             # Sistema de votos crowdsourced
│   ├── DEPLOY_DOKPLOY.md               # Procedimiento de deploy
│   └── MAPEO_RUBRICA.md                # Vinculación docs ↔ rúbrica residencia
│
├── deploy/
│   └── DOKPLOY.md                      # Guía operativa de deploy
│
├── Dockerfile                          # Multi-stage (Node builder + Python runtime)
├── entrypoint.sh                       # Wait-for-DB + supercronic + node server.js
├── crontab.txt                         # 3 cron jobs (supercronic)
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── package.json                        # quiniela-frontend v0.1.0
├── requirements.txt                    # Deps Python (pinned 2026-09-09)
├── .dockerignore
├── .env.example
├── ARCHITECTURE.md                     # Decisiones de diseño + diagrama
└── README.md                           # Este archivo
```

---

## 🔐 Seguridad

### Backend
- ✅ Token SportMonks en `.env` con permisos `600`, nunca en logs
- ✅ `.env` excluido del repo vía `.gitignore`
- ✅ Crons bash puros (no LLM, no exponen tokens)
- ✅ Sanitización de errores en prompts LLM (commit `84c8b61`)
- ✅ Queries SQL parametrizadas (commit `84c8b61`)

### Frontend
- ✅ **Validación regex anti-SQLi** (`^\d{1,10}$`) en IDs de URL (`lib/validation.ts`)
- ✅ **Cookies HttpOnly + SameSite=Lax** para votante (180d)
- ✅ **Hash de identidad votante**: `sha256(cookie + ip_prefix + ua_fingerprint)[:32]`
- ✅ **Tokens opacos de 8 chars base32** (sha256 truncated, requieren SECRET_SALT)
- ✅ **BD read-only** (mejor-sqlite3 `readonly: true, fileMustExist: true`)
- ✅ **BD de votos separada** (RW, journal_mode WAL, autocheckpoint)
- ✅ Sin IPs crudas ni UAs completos guardados (solo fingerprints)

### Deploy
- ✅ HTTPS forzado (Traefik + cert wildcard `*.barberia.date`)
- ✅ Container Dokploy con `app` no-root (UID 1000)
- ✅ Bind-mount con permisos restrictivos

---

## 🛠️ Comandos útiles

```bash
# Backend — estado de la BD
python3 -c "
from sqlalchemy import select, func
from src.db import get_session, Base
S = get_session()
with S() as s:
    for t in sorted(Base.metadata.tables):
        cnt = s.execute(select(func.count()).select_from(Base.metadata.tables[t])).scalar()
        print(f'  {t:<25} {cnt:>10,}')
"

# Backend — test conexión SportMonks
python3 -m src.test_connection

# Backend — backup manual antes de cambios importantes
cp /workspace/proyectos/data/predictions_mx.db \
   /workspace/proyectos/data/predictions_mx.\$(date +%Y%m%d_%H%M%S).backup.db

# Backend — recalibrar Platt manualmente
bash scripts/recalibrate_platt.sh

# Backend — pipeline manual (sin esperar cron)
python3 scripts/full_pipeline.py

# Frontend — dev server
npm run dev

# Frontend — build standalone (Docker)
npm run build

# Tests — correr todos (~30s)
python3 -m pytest tests/

# Tests — un archivo específico
python3 -m pytest tests/test_ensemble.py -v

# Deploy — ver logs del container Dokploy
docker logs predicciones-mx-app-XXXXX --tail 50

# Deploy — verificar healthcheck
curl https://predicciones.barberia.date/api/health
```

---

## 📚 Documentación

| Doc | Contenido |
|---|---|
| [`README.md`](./README.md) | Este archivo — overview + quick start + estado actual |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Decisiones de diseño + diagrama detallado |
| [`docs/ROADMAP.md`](./docs/ROADMAP.md) | Roadmap completo (Fases 1-D) |
| [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) | Cómo funciona el modelo (features, ensemble, Platt) |
| [`docs/BACKTESTING_RESULTS.md`](./docs/BACKTESTING_RESULTS.md) | Métricas empíricas + Fase B resultados |
| [`docs/FEATURES.md`](./docs/FEATURES.md) | Catálogo de 28 features engineered |
| [`docs/SCHEMA_V2.md`](./docs/SCHEMA_V2.md) | Diseño de las 19 tablas |
| [`docs/RESEARCH_SYNTHESIS.md`](./docs/RESEARCH_SYNTHESIS.md) | Papers revisados (Dixon-Coles, FiveThirtyEight, etc.) |
| [`docs/ARTICLES_INVENTORY.md`](./docs/ARTICLES_INVENTORY.md) | Inventario bibliográfico |
| [`docs/SOURCES_AUDIT.md`](./docs/SOURCES_AUDIT.md) | Qué cubre SportMonks vs qué falta |
| [`docs/ARCHITECTURE_FRONTEND.md`](./docs/ARCHITECTURE_FRONTEND.md) | Sistema Next.js (rutas, API, BD read-only) |
| [`docs/QUINIELAS_SYSTEM.md`](./docs/QUINIELAS_SYSTEM.md) | Sistema de votos crowdsourced |
| [`docs/DEPLOY_DOKPLOY.md`](./docs/DEPLOY_DOKPLOY.md) | Procedimiento deploy Dokploy |
| [`docs/MAPEO_RUBRICA.md`](./docs/MAPEO_RUBRICA.md) | Vinculación docs ↔ rúbrica residencia |

---

## 🤝 Contribución

Este es un proyecto personal de Ángel Padilla. Decisiones se toman considerando:
- Tiempo del propietario (no abusar)
- Presupuesto ($0 APIs externas adicionales, solo SportMonks custom)
- Calidad de datos (auditados contra docs oficiales)
- Privacidad (nada de tokens en logs/repo, fingerprints en vez de IPs crudas)

---

**Última actualización:** 2026-09-10 (merge frontend + deploy Dokploy + recalibración Platt)  
**Mantenedor:** Predictions_MX agent (@Predictions_MX_bot)  
**Estado:** 🟢 Activo — Fase B.1 (Platt scaling) + Fase A (frontend + quinielas) + Fase C0 (deploy Dokploy) completas
