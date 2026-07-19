# ⚽ Predictions_MX — Sistema Profesional de Predicciones Liga MX

> **Bot:** [@Predictions_MX_bot](https://t.me/Predictions_MX_bot) · **Owner:** Ángel Padilla · **Última actualización:** 2026-07-19

Sistema profesional de predicciones para la **Liga MX**, construido sobre datos de **[SportMonks v3](https://www.sportmonks.com/)** con pipeline automatizado de ingesta → predicción → publicación.

---

## 🎯 ¿Qué es esto?

Dos sistemas integrados en un workspace:

1. **Backend de predicciones** (este repo): ingesta SportMonks, modelo ensemble, calibración Platt, validación out-of-sample, reportes Telegram.
2. **Frontend público** ([quinielas.lol](https://quinielas.lol), repo separado): visualización web + sistema de votaciones crowdsourced de la comunidad.

**Objetivo:** predecir resultados de Liga MX con accuracy >50% (baseline aleatorio 33%, estado del arte ≈55-60%) usando features engineered y calibración estadística.

---

## ⚡ Quick Start

```bash
# Variables de entorno (Ángel tiene el token)
cp .env.example .env
# Editar .env con SPORTMONKS_API_TOKEN

# Dependencias
pip3 install --break-system-packages requests pandas numpy sqlalchemy python-dotenv scipy scikit-learn

# Pipeline diario (corre automático 11:00 UTC vía cron OpenClaw)
python3 scripts/full_pipeline.py

# Validar resultados (corre semanal lunes 09:00 UTC vía cron container)
python3 scripts/recalibrate_platt.sh

# Predicción ad-hoc (próximos partidos)
python3 src/predict/cli.py --match "América vs Chivas"
```

---

## 📊 Estado actual (julio 2026)

### Métricas live (Fase B con Platt scaling)

| Métrica | Pre Platt | **Post Platt** | Δ vs baseline |
|---|---|---|---|
| Accuracy OOS (n=994, 3 temp) | 50.6% | **51.1%** | +18pp vs 33% random |
| Brier /3 | 0.2042 | **0.2009** | -0.33pp |
| Log Loss | 1.0203 | **1.0158** | -0.0045 |

Calibración excelente por tier:
- High (60-70%, n=7): 85.7% acc
- Medium (50-60%, n=8): 50% acc
- Low (<50%, n=38): 39.5% acc (random)

### Modelos

- **Ensemble** (xg + Elo + Dixon-Coles + heur) — baseline 50.17% acc OOS
- **Platt scaling 1-vs-rest** — calibración de probabilidades (Fase B.1)
- **Recalibrador automático semanal** — lunes 09:00 UTC, rollback si Δ Brier >1pp
- **28 features engineered** + **15 heurísticas**

### Tablas BD (SQLite: `data/predictions_mx.db`)

| Tabla | Registros | Fuente |
|---|---:|---|
| `fixtures` | 3,143 | SportMonks |
| `seasons` | 44 | SportMonks |
| `teams` | 47 | SportMonks |
| `venues` | 45 | SportMonks + manual |
| `players` | 2,492 | SportMonks |
| `coaches` | 285 | SportMonks |
| `coach_tenures` | 1,082 | SportMonks |
| `fixture_events` | 53,770 | SportMonks |
| `fixture_statistics` | 192,370 | SportMonks |
| `fixture_lineups` | 127,186 | SportMonks |
| `analyst_predictions` | live + backtest | Calculado |
| `market_odds` | 14d rolling | MVP sintético (Fase A.3) |
| `player_injuries` | activo | ESPN API (Fase 10.5) |
| `match_weather` | próximos 7d | Open-Meteo |

**Ligas:** Liga MX (id=743) — 6 temporadas scrapeadas (2021-2027 parcial).

---

## 🏗️ Arquitectura (high-level)

```
┌─────────────────────────────────────────────────────────────────┐
│                       SPORTMONKS API v3                          │
│  Plan Ángel: 3,000 calls/hora                                    │
│  Endpoints: fixtures, lineups, statistics, events, etc.          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         sportmonks_client.py (rate-limited, includes)            │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼─────────────────────┐
        ▼                    ▼                     ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│   Ingesta    │   │   Ingesta ESPN   │   │   Ingesta ODDS   │
│  (fixtures,  │   │   (lesiones MX)  │   │  (mercado MVP)   │
│  lineups,    │   │                  │   │                  │
│  stats)      │   │                  │   │                  │
└──────┬───────┘   └────────┬─────────┘   └────────┬─────────┘
       │                    │                      │
       └────────────────────┼──────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  SQLite (data/predictions_mx.db)                │
│                  19 tablas (schema v2)                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Feature Engineering                             │
│  - Home/away split, exponential form, h2h, altitude             │
│  - Rest days, fixture congestion, coach tenure                   │
│  - Referee bias, attendance ratio, weather                       │
│  - Player injuries impact                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│            ENSEMBLE (xg + Elo + Dixon-Coles + heur)             │
│                  Pesos: 0.55/0.225/0.135/0.09                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PLATT SCALING (calibración)                     │
│                  1-vs-rest por clase (Fase B.1)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Sistema de Predicción → 3 destinos                  │
│  1. BD: analyst_predictions (backtest, reconciliation)           │
│  2. Reporte diario: data/daily_report.txt + Telegram             │
│  3. Frontend: quinielas.lol (read-only BD bind)                 │
└─────────────────────────────────────────────────────────────────┘
```

**Crón jobs:**
- `0 11 * * * UTC` — Pipeline diario (OpenClaw cron, me despierta)
- `0 4 * * * UTC` — Backup BD (crontab container, bash puro)
- `0 9 * * 1 UTC` — Recalibrar Platt (crontab container, lunes)

Ver [`ARCHITECTURE.md`](./ARCHITECTURE.md) para detalle completo.

---

## 🗺️ Roadmap

### ✅ Completado

- **Fase 1-5**: Schema, ingesta, modelos base, calibración, backtesting (2026)
- **Fase 6-9**: Recalibración Platt, threshold mínimo, attendance heur, referee bias, weather ingest, xG proxy
- **Fase 10.1-10.3**: Sistema multi-agente debate (Bull/Bear/Numérico/Contextual/Auditor + Juez DWC-MAD)
- **Fase A**: quinielas.lol frontend LIVE, sistema de votos Sprint 4, market odds MVP
- **Fase B.1**: Platt scaling en producción, recalibrador automático semanal (jul 2026)
- **Fix**: paso C1b refresh fixtures resultados (bugfix jul 2026)

### 🔄 En progreso (Fase B.2)

- Recency weighting en fit Platt (drift temporal)
- CLV tracker (cuando odds reales disponibles)

### 📅 Planeado (Fase C/D)

- **Fase C** (1 mes): drift detection, autotrain, lesiones ESPN avanzadas
- **Fase D** (2-3 meses): tracking data, reports semanales, quiniela.lol v2

Ver [`docs/ROADMAP.md`](./docs/ROADMAP.md) para detalle completo.

---

## 📁 Estructura del proyecto

```
proyectos/
├── src/                                # Código fuente Python
│   ├── config.py                       # Config desde .env
│   ├── sportmonks_client.py            # Cliente HTTP rate-limited
│   ├── db.py                           # 19 modelos SQLAlchemy (schema v2)
│   ├── ingest_*.py                     # Scripts de ingesta (SportMonks, ESPN)
│   ├── predict/                        # Sistema de predicción
│   │   ├── features.py                 # 28 features engineered
│   │   ├── elo.py                      # Elo rating (FiveThirtyEight style)
│   │   ├── dixon_coles.py              # Poisson + τ
│   │   ├── xg.py                       # xG proxy (Ridge log-link)
│   │   ├── heuristics.py               # 15 heurísticas
│   │   ├── backtest.py                 # Validación OOS
│   │   ├── populate_analyst_predictions.py  # Genera live + backtest
│   │   └── calibration.py              # Platt scaling (Fase B.1)
│   ├── agents/                         # Multi-agente debate (Fase 10)
│   └── ...
│
├── scripts/                            # Scripts de operación
│   ├── full_pipeline.py                # Pipeline diario (10 pasos)
│   ├── reconcile_outcomes.py           # Reconcilia predicción vs realidad
│   ├── refresh_fixtures_results.py     # C1b: actualiza resultados SportMonks
│   ├── recalibrate_platt.sh            # Recalibrador semanal (cron lunes)
│   ├── build_calibration_dataset.py    # Genera CSV para fit Platt
│   ├── fit_platt_scaling.py            # Ajuste Platt + OOS eval
│   ├── fit_isotonic.py                 # Comparación Platt vs Isotonic
│   ├── coach_change_alert.py           # Detecta cambios DT
│   └── backup_db.sh                    # Backup diario BD (cron)
│
├── data/
│   ├── predictions_mx.db               # BD principal (~272 MB)
│   ├── calibracion_dataset.csv         # Temp para fit Platt
│   ├── platt_coefficients.json         # Coefs calibrados
│   ├── mx_coefficients.json            # Pesos ensemble + shrinkage
│   ├── daily_report.{json,txt}         # Reporte diario (Telegram-ready)
│   ├── backups/                        # Últimos 3 backups BD
│   └── logs/                           # Logs estructurados
│
├── docs/
│   ├── ROADMAP.md                      # Roadmap completo
│   ├── METHODOLOGY.md                  # Cómo funciona el modelo
│   ├── BACKTESTING_RESULTS.md          # Métricas empíricas
│   ├── FEATURES.md                     # Catálogo de 28 features
│   ├── SCHEMA_V2.md                    # Diseño BD
│   ├── RESEARCH_SYNTHESIS.md           # Papers revisados
│   ├── ARTICLES_INVENTORY.md           # Inventario bibliográfico
│   └── SOURCES_AUDIT.md                # Auditoría de fuentes
│
├── models/                             # Modelos ML entrenados
├── tests/                              # 42+ tests unitarios (~5.5s)
├── .env.example                        # Plantilla variables entorno
└── README.md                           # Este archivo
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

---

## 🔐 Seguridad

- ✅ Token SportMonks en `.env` con permisos `600`
- ✅ `.env` excluido del repo vía `.gitignore`
- ✅ Token NUNCA se imprime en logs
- ✅ BD con permisos restrictivos (RO bind para frontend quiniela.lol)
- ✅ Crons bash puros sin LLM (no exponen tokens)

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

# Test conexión SportMonks
python3 -m proyectos.src.test_connection

# Backup manual antes de cambios importantes
cp /workspace/proyectos/data/predictions_mx.db \
   /workspace/proyectos/data/predictions_mx.$(date +%Y%m%d_%H%M%S).backup.db

# Logs
tail -f /workspace/proyectos/data/predictions_mx.log
tail -f /workspace/proyectos/data/logs/cron_recalibrate.log
```

---

## 🤝 Contribución

Este es un proyecto personal de Ángel Padilla. Decisiones se toman considerando:
- Tiempo del propietario (no abusar)
- Presupuesto ($0 APIs externas, solo SportMonks custom)
- Calidad de datos (auditados contra docs oficiales)
- Privacidad (nada de tokens en logs/repo)

---

**Última actualización:** 2026-07-19 (Fase B.1 Platt scaling + recalibrador + fix pipeline C1b)
**Mantenedor:** Predictions_MX agent (@Predictions_MX_bot)
**Estado:** 🟢 Activo — Fase A (frontend quiniela.lol) + Fase B.1 (Platt scaling) completas