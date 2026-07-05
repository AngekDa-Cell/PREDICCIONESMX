# ⚽ Predictions_MX — Sistema Profesional de Predicciones Liga MX

> **Bot:** [@Predictions_MX_bot](https://t.me/Predictions_MX_bot) · **Owner:** Ángel Padilla · **Última actualización:** 2026-06-26

Sistema profesional de predicciones para la **Liga MX** (y Liga de Expansión MX), construido sobre datos de **[SportMonks v3](https://www.sportmonks.com/)** + enriquecido con APIs externas y curación manual para análisis profundo.

---

## 🎯 ¿Qué es esto?

No es solo "predicción de goles". Es un **sistema de análisis profundo** que combina:

- 📊 **Estadísticas detalladas** de cada partido (78 stats por equipo)
- 👤 **Datos individuales** de jugadores (rating, posición, minutos, goles)
- 🧠 **Contexto humano** (forma reciente, presión del DT, fatiga)
- 🏟️ **Contexto físico** (altitud del estadio, clima, viaje)
- 🎭 **Contexto emocional** (derby, clásico, presión mediática — vía manual)

El objetivo: **predecir resultados de partidos de Liga MX con features de nivel profesional**, no amateur.

---

## ⚡ Quick Start

```bash
# 1. Variables de entorno (¡solo Ángel tiene el token!)
cp .env.example .env
# Editar .env y pegar SPORTMONKS_API_TOKEN

# 2. Instalar dependencias
pip3 install --break-system-packages requests pandas numpy sqlalchemy python-dotenv

# 3. Inicializar BD (crea las 19 tablas)
python3 -m proyectos.src.init_db

# 4. Ingerir datos
python3 -m proyectos.src.test_connection      # verificar API
python3 -m proyectos.src.ingest_leagues        # 2 ligas
python3 -m proyectos.src.ingest_seasons        # 44 temporadas
python3 -m proyectos.src.ingest_seasons_targeted  # fixtures + events + stats (5 temporadas × 2 ligas)
python3 -m proyectos.src.ingest_statistics     # 192K stats detalladas
python3 -m proyectos.src.ingest_coaches        # 285 coaches + 1,082 tenures
python3 -m proyectos.src.ingest_lineups        # 127,186 alineaciones + players
python3 -m proyectos.src.ingest_venues         # 45 venues con altitud real
```

---

## 📊 Estado actual del proyecto

```
📦 BASE DE DATOS (SQLite: data/predictions_mx.db)
══════════════════════════════════════════════════════════════
  19 tablas totales (schema v2)
  15 con datos scrapeados de SportMonks
   4 pendientes de calcular (forms, context, travel)
```

### Tablas y conteos actuales (junio 2026):

| Tabla | Registros | Fuente | Status |
|---|---:|---|:---:|
| `leagues` | 2 | SportMonks | ✅ |
| `seasons` | 44 | SportMonks | ✅ |
| `teams` | 47 | SportMonks | ✅ |
| `venues` | 45 | SportMonks + manual | ✅ |
| `players` | 2,492 | SportMonks | ✅ |
| `coaches` | 285 | SportMonks | ✅ |
| `coach_tenures` | 1,082 | SportMonks | ✅ |
| `fixtures` | 3,081 | SportMonks | ✅ |
| `fixture_events` | 53,770 | SportMonks | ✅ |
| `fixture_statistics` | 192,370 | SportMonks | ✅ |
| `fixture_lineups` | 127,186 | SportMonks | ✅ |
| `referees` | (pendiente) | SportMonks | ⏳ |
| `player_injuries` | 0 | Scraping ESPN MX | ⏳ |
| `player_transfers` | 0 | SportMonks | ⏳ |
| `match_weather` | 0 | Open-Meteo | ⏳ |
| `match_context` | 0 | Calculado + manual | ⏳ |
| `travel_log` | 0 | Calculado | ⏳ |
| `team_form` | 0 | Calculado | ⏳ |
| `player_form` | 0 | Calculado | ⏳ |
| `coach_form` | 0 | Calculado | ⏳ |

**Ligas cubiertas:**
- 🇲🇽 **Liga MX** (id=743) — 1,701 fixtures históricos
- 🇲🇽 **Liga de Expansión MX** (id=749) — 1,380 fixtures históricos

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                       SPORTMONKS API v3                          │
│  Custom Plan de Ángel: 3,000 calls/hora                          │
│  Ligas: Liga MX (743) + Liga Expansión (749)                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  sportmonks_client.py                            │
│  - Rate limiting (ventana móvil 1h)                              │
│  - Retries con backoff exponencial                               │
│  - Sistema de `includes` anidados                                │
│  - Paginación por cursor                                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│            Scripts de ingesta (src/ingest_*.py)                  │
│  - leagues, seasons, fixtures, events, statistics                │
│  - coaches, coach_tenures, lineups                               │
│  - venues, metadata (formations, attendance)                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQLite (data/predictions_mx.db)            │
│  19 tablas (ver tabla arriba)                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
   ┌─────────────────────┐       ┌─────────────────────────┐
   │ Feature engineering │       │ Cálculo de forms         │
   │ (scripts python)    │       │ (team/player/coach)      │
   └──────────┬──────────┘       └────────────┬────────────┘
              │                               │
              └─────────────┬─────────────────┘
                            ▼
              ┌──────────────────────────────┐
              │   MODELO ML                  │
              │   - Poisson bivariado (MVP)  │
              │   - XGBoost / LightGBM       │
              │   - Ensemble                 │
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  Reportes / Telegram Bot      │
              │  (este chat con @angelpadilla)│
              └──────────────────────────────┘
```

---

## 🗺️ Roadmap

### ✅ Fase 1 — Schema v2 + Datos scrapeados (COMPLETADA)
- 19 tablas diseñadas (8 mejoradas + 11 nuevas)
- Migración preservando 3,081 fixtures + 53,770 events + 192,370 stats
- Ingesta de coaches, lineups, venues con altitud real de México

### 🔄 Fase 2 — Más datos scrapeables (EN PROGRESO)
- [ ] `ingest_metadata.py` — Formations + attendance de cada fixture
- [ ] `ingest_referees.py` — Árbitros por temporada
- [ ] `ingest_transfers.py` — Transferencias por equipo
- [ ] `ingest_standings.py` — Tabla de posiciones por temporada
- [ ] `ingest_topscorers.py` — Goleadores con player + team
- [ ] `ingest_weather.py` — Weather histórico vía Open-Meteo (gratis)

### 📝 Fase 3 — Cálculo de features + curación manual
- [ ] `compute_team_form.py` — Forma últimos 5 partidos
- [ ] `compute_player_form.py` — Forma/goles/asist por jugador
- [ ] `compute_coach_form.py` — Racha DT + presión
- [ ] `compute_match_context.py` — Derby, descanso, consecutivos
- [ ] `compute_travel_log.py` — Distancia desde venue anterior
- [ ] `data/manual/coach_tactics.json` — tactical_style + formation (manual)
- [ ] `data/manual/stadium_surface.json` — surface/roof (manual)
- [ ] `data/manual/team_context.json` — Presiones especiales

### 🤖 Fase 4 — Scraping avanzado (opcional)
- [ ] `scrape_transfermarkt.py` — Tactical style del DT
- [ ] `scrape_espn_injuries.py` — Lesiones de jugadores MX

### 🚀 Fase 5 — Modelo ML
- [ ] **MVP:** Poisson bivariado (baseline)
- [ ] **XGBoost / LightGBM** con features engineered
- [ ] **Ensemble** (Poisson + XGBoost + Dixon-Coles)
- [ ] **Backtest** con histórico 2021-2026
- [ ] **Predicciones en vivo** de próxima jornada
- [ ] **Reportes automatizados** vía Telegram

---

## 📁 Estructura del proyecto

```
proyectos/
├── src/                           # Código fuente Python
│   ├── config.py                  # Config desde .env
│   ├── logging_setup.py           # Logging a consola + archivo rotativo
│   ├── sportmonks_client.py       # Cliente HTTP con rate-limit + retries
│   ├── db.py                      # 19 modelos SQLAlchemy (schema v2)
│   ├── init_db.py                 # Crea las tablas
│   ├── migrate_v2.py              # Migración v1 → v2 preservando datos
│   ├── test_connection.py         # Prueba el token
│   ├── ingest_leagues.py          # Liga MX + Expansión
│   ├── ingest_seasons.py          # Temporadas
│   ├── ingest_seasons_targeted.py # Equipos + fixtures + eventos (5 temporadas)
│   ├── ingest_statistics.py       # Stats detalladas por partido
│   ├── ingest_coaches.py          # Coaches + tenures
│   ├── ingest_lineups.py          # Alineaciones + players
│   ├── ingest_venues.py           # Venues + altitud/coords
│   └── ...                        # Más scripts de ingesta (Fase 2+)
│
├── data/
│   ├── predictions_mx.db          # BD principal (SQLite, 175 MB)
│   ├── predictions_mx.v1_backup.db # Backup de v1 (por seguridad)
│   ├── predictions_mx.log         # Log rotativo
│   ├── stat_type_mapping.json     # Cache de tipos de stats
│   ├── venue_elevation_cache.json # Cache de altitudes Open-Meteo
│   ├── raw/                       # Datos crudos (futuro)
│   ├── processed/                 # Datos procesados
│   └── historical/                # Histórico consolidado
│
├── models/                        # Modelos ML entrenados (Fase 5)
├── tests/                         # Tests unitarios
├── docs/
│   ├── SCHEMA_V2.md               # Diseño detallado del schema
│   ├── SCHEMA_V2_VISUAL.txt       # Diagrama visual ASCII
│   └── SOURCES_AUDIT.md           # Auditoría de fuentes de datos
│
├── .env.example                   # Plantilla de variables de entorno
├── .gitignore                     # Exclusiones (.env, *.db, etc.)
├── ARCHITECTURE.md                # Arquitectura detallada
└── README.md                      # Este archivo
```

---

## 📚 Documentación

| Doc | Contenido |
|---|---|
| [`README.md`](./README.md) | Este archivo — overview + quick start + roadmap |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Decisiones de diseño + diagrama detallado |
| [`docs/SCHEMA_V2.md`](./docs/SCHEMA_V2.md) | Diseño de las 19 tablas (incluye ER diagram) |
| [`docs/SCHEMA_V2_VISUAL.txt`](./docs/SCHEMA_V2_VISUAL.txt) | Diagrama visual ASCII del schema |
| [`docs/SOURCES_AUDIT.md`](./docs/SOURCES_AUDIT.md) | Qué cubre SportMonks vs qué hay que scrapear |

---

## 🔐 Seguridad

- ✅ Token de SportMonks en `.env` con permisos `600`
- ✅ `.env` excluido del repo vía `.gitignore`
- ✅ Token NUNCA se imprime en logs
- ✅ Backup de v1 preservado en `data/predictions_mx.v1_backup.db`
- ✅ DB con permisos restrictivos para lectura/escritura

---

## 🎯 Ligas objetivo (Custom Plan de Ángel)

| Liga | SportMonks ID | Cobertura histórica |
|---|---|---|
| Mexico (categoría padre) | **458** | (referencia) |
| **Liga MX** | **743** | 22 temporadas (2005-2026) |
| **Liga de Expansión MX** | **749** | 22 temporadas (2005-2026) |

**Límite del plan:** 3,000 calls/hora
**Status actual:** ~2,940 calls/hora disponibles (usamos ~60 en ingesta inicial)

---

## 🛠️ Comandos útiles

```bash
# Estado de la BD
python3 -c "
import sys; sys.path.insert(0, '/workspace')
from sqlalchemy import select, func
from proyectos.src.db import get_session, Base
S = get_session()
with S() as s:
    for t in sorted(Base.metadata.tables):
        cnt = s.execute(select(func.count()).select_from(Base.metadata.tables[t])).scalar()
        print(f'  {t:<25} {cnt:>10,}')
"

# Backup antes de cambios importantes
cp /workspace/proyectos/data/predictions_mx.db \
   /workspace/proyectos/data/predictions_mx.$(date +%Y%m%d_%H%M%S).backup.db

# Ver logs
tail -f /workspace/proyectos/data/predictions_mx.log

# Probar conexión al API sin gastar muchas calls
python3 -m proyectos.src.test_connection
```

---

## 🤝 Contribución

Este es un proyecto personal de Ángel Padilla. Las decisiones se toman considerando:
- Tiempo del propietario (no abusar)
- Presupuesto ($0 en APIs externas, solo SportMonks custom)
- Calidad de datos (auditados contra docs oficiales)
- Privacidad (nada de tokens en logs/repo)

---

**Última actualización:** 2026-06-26
**Mantenedor:** Predictions_MX agent (@Predictions_MX_bot)
**Estado:** 🟢 Activo — Fase 1 completa, Fase 2 en progreso