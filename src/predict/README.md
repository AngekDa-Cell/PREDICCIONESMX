# Predictions_MX — Sistema de Predicción (Backend)

> Sistema profesional de predicción de partidos de Liga MX.
> Última actualización: 2026-09-10 (Fase B.1 Platt scaling + 28 features + 15 heurísticas + xG proxy + debate multi-agente)

---

## 🎯 Overview

Predictions_MX es el **backend Python** del sistema completo. Combina:

- **4 modelos estadísticos** (Dixon-Coles, Elo Rating, xG proxy, heurísticas)
- **28 features engineered** validadas científicamente
- **15 heurísticas** del dominio Liga MX (calibradas con datos propios)
- **Platt scaling 1-vs-rest** (calibración de probabilidades)
- **Debate multi-agente** (5 agentes LLM + juez DWC-MAD, experimental)
- **Recalibración automática semanal** con rollback

**Estado actual (septiembre 2026):**
- Accuracy OOS live (Platt): **51.1%** (n=994, 3 temporadas)
- Brier Score /3: **0.2009**
- Log Loss: **1.0158**
- Backtest 2024-2025 (680 partidos, xG + attendance): **52.21% acc, 0.6092 Brier**
- Backtest 2025 aislado (340 partidos, con heur attendance): **53.82% acc**
- **257 tests pasando** en ~30s

---

## 🚀 Quick Start

### Predicción rápida
```bash
python3 src/predict/cli.py --home "América" --away "Chivas"
```

### Head-to-head
```bash
python3 src/predict/cli.py --h2h --home "Tigres" --away "Rayados"
```

### Con narrativa del usuario
```bash
python3 src/predict/cli.py --home "Pachuca" --away "Tijuana" \
  --narrative "DT nuevo de Tijuana, sistema táctico nuevo"
```

### Backtesting
```bash
python3 src/predict/backtest.py --last-n 100
python3 src/predict/backtest.py --start 2024-01-01 --end 2025-12-31
```

### Estado y reporte
```bash
python3 src/predict/cli.py --validate
python3 src/predict/cli.py --report
python3 src/predict/cli.py --recent 5
```

### Ajuste de Platt scaling
```bash
# Fit con últimos 800 partidos
python3 scripts/fit_platt_scaling.py

# Eval OOS leave-one-season-out
python3 scripts/fit_platt_scaling.py --eval

# Recalibrar con rollback automático (lunes 09:00 UTC vía cron)
bash scripts/recalibrate_platt.sh
```

---

## 📁 Estructura

```
src/predict/
├── __init__.py                       # Interfaz pública
├── cli.py                            # CLI principal
├── features.py                       # 28 features engineered
├── elo.py                            # Rating Elo dinámico + shrinkage
├── elo_shrinkage.py                  # Grid search shrinkage global
├── team_local_shrinkage.py           # Shrinkage por equipo/localía
├── dixon_coles.py                    # Modelo Poisson + corrección τ
├── xg.py                             # xG proxy (Ridge log-link)
├── heuristics.py                     # 15 reglas del analista
├── referee_bias.py                   # Sesgo arbitral documentado
├── backtest.py                       # Sistema de backtesting
├── backtest_xg.py                    # Backtest específico xG
├── backtest_with_injuries.py         # Backtest con lesiones
├── backtest_attendance.py            # Backtest con attendance
├── backtest_by_team.py               # Diagnóstico por equipo
├── backtest_referee.py               # Backtest con referee bias
├── backtest_compare.py               # Comparativa múltiples configs
├── calibration.py                    # Platt scaling (apply_calibration)
├── calibration_xg.py                 # Calibración xG
├── recalibration.py                  # Recalibrador semanal
├── stacking.py                       # XGBoost stacking (NO adoptado)
├── stacking_walkforward.py           # Walk-forward stacking (NO adoptado)
├── analyst_log.py                    # Bitácora de predicciones
├── misc_utils.py                     # Utilities
├── mx_coefficients.json              # Calibraciones MX
└── README.md                         # Este archivo
```

```
src/agents/                           # Multi-agente debate (Fase 10)
├── orchestrator.py                   # 3-agentes (Bull, Bear, Numérico) + juez
├── orchestrator_live.py              # Con LLM real (paralelo)
├── judge.py                          # DWC-MAD v2 (5-agentes)
├── contextual.py                     # Agente noticias (web_search)
├── data_auditor.py                   # Validador integridad
├── feature_block.py                  # 8 features inyectadas a prompts
├── prompts.py                        # Templates prompts
├── permissions.py                    # Permisos estrictos
└── simulator.py                      # Modo simulate (sin LLM)
```

```
data/
├── predictions_mx.db                 # BD principal SQLite (272 MB)
├── platt_coefficients.json           # Coefs Platt actuales
├── mx_coefficients.json              # Pesos ensemble + shrinkage
├── daily_report.{json,txt}           # Reporte diario (Telegram-ready)
├── multi_agent_*.json                # Logs de debates multi-agente
├── backtest_*.json                   # Resultados de backtests
└── ...
```

```
scripts/                              # Operación
├── full_pipeline.py                  # Pipeline diario (10 pasos + quick wins)
├── reconcile_outcomes.py             # Pred vs realidad
├── refresh_fixtures_results.py       # C1b: refresh resultados
├── recalibrate_platt.sh              # Recalibrador semanal
├── backup_db.sh                      # Backup diario (cron 04 UTC)
├── fit_platt_scaling.py              # Fit + eval OOS Platt
├── fit_isotonic.py                   # Comparación Platt vs Isotonic
├── build_calibration_dataset.py      # Genera CSV para fit
├── coach_change_alert.py             # Detecta cambios DT
└── ...
```

```
docs/                                 # Documentación técnica
├── METHODOLOGY.md                    # Cómo funciona el modelo
├── FEATURES.md                       # Catálogo de 28 features
├── BACKTESTING_RESULTS.md            # Resultados empíricos
├── ROADMAP.md                        # Roadmap completo
├── RESEARCH_SYNTHESIS.md             # Papers revisados
├── ARTICLES_INVENTORY.md             # Inventario bibliográfico
└── SOURCES_AUDIT.md                  # Cobertura de fuentes
```

---

## 📊 Modelos implementados

### 1. Dixon-Coles (1997)

- Poisson bivariado para goles
- Corrección τ para scorelines bajos (0-0, 1-1)
- Parámetros: attack, defense, home_advantage, ρ
- Implementación: `dixon_coles.py`

### 2. Elo Rating (FiveThirtyEight style)

- K-factor con multiplier por goal difference
- Home advantage: 100 puntos
- **Shrinkage global 0.7** (calibrado Fase 6, grid search)
- Shrinkage por equipo/localía (experimental)
- Implementación: `elo.py`, `elo_shrinkage.py`, `team_local_shrinkage.py`

### 3. xG Proxy (Fase 8, Ridge log-link)

- Regresión Ridge con stats agregados SportMonks (no shot-level)
- Features: shots-on-target, shots-insidebox, shots-blocked, shot_quality, is_home
- Decay exponencial 0.85 (rolling)
- **Modelo individual más fuerte** (51.91% acc, 0.6173 Brier)
- Coefs calibrados con 3,830 equipo-partidos Liga MX
- Correlación in-sample con goles reales: 0.553
- Implementación: `xg.py`, `backtest_xg.py`, `calibration_xg.py`

### 4. Heurísticas (15 reglas)

| # | Heurística | Impacto |
|---|---|---|
| 1 | Altitud MX (+2.48%/1000m) | Significativo |
| 2 | Derby detection (6 derbies) | Moderado |
| 3 | Derby flatten (-15%) | Moderado |
| 4 | Presión DT (winless ≥5) | Moderado |
| 5 | Forma streak (W/L ≥3) | Moderado |
| 6 | Travel fatigue (>1500km) | Moderado |
| 7 | Fixture congestion (3+ en 7d) | Bajo-Moderado |
| 8 | Coach tenure (new manager bounce) | Moderado |
| 9 | Momentum score (decay exp) | Moderado |
| 10 | H2H dominance (>65%) | Moderado |
| 11 | Narrativas del usuario | Configurable |
| 12 | Composite momentum (Fase 6) | Bajo (+0.04% NLL) |
| 13 | Weather impact (Open-Meteo) | Bajo (cuantitativo bajo) |
| 14 | Referee bias documentado | Cualitativo |
| 15 | **Attendance inverted** (Fase 9) | +0.29pp acc (2025) |

### Ensemble (Fase 8 — pesos calibrados vía grid search)

```
ensemble_probs = 0.55 × xG + 0.225 × Elo + 0.135 × Dixon-Coles + 0.09 × heur
```

**Individual vs Ensemble (backtest 2024-2025, 680 partidos):**

| Modelo | Accuracy | Brier |
|---|---|---|
| **xG proxy** | **51.91%** | 0.6173 |
| Elo Rating (con shrinkage) | 48.97% | 0.6047 |
| Dixon-Coles | 41.91% | 0.6631 |
| Heurísticas | 40.74% | 0.6593 |
| **Ensemble (sin Platt)** | 52.21% | 0.6092 |
| **Ensemble + Platt (live)** | **51.1%** (n=994 OOS) | **0.2009** |

---

## 📚 Documentación adicional

- [`docs/METHODOLOGY.md`](../../docs/METHODOLOGY.md) — Cómo funciona el modelo (features, ensemble, Platt, xG, debate)
- [`docs/FEATURES.md`](../../docs/FEATURES.md) — Catálogo completo de 28 features
- [`docs/BACKTESTING_RESULTS.md`](../../docs/BACKTESTING_RESULTS.md) — Resultados empíricos detallados
- [`docs/RESEARCH_SYNTHESIS.md`](../../docs/RESEARCH_SYNTHESIS.md) — Papers revisados
- [`docs/ROADMAP.md`](../../docs/ROADMAP.md) — Roadmap completo (Fase 1-D)

---

## 🎯 Validación

```bash
# Correr todos los tests (~30s)
python3 -m pytest tests/

# Tests específicos
python3 -m pytest tests/test_ensemble.py -v
python3 -m pytest tests/test_xg.py -v
python3 -m pytest tests/test_recalibration.py -v

# Conteo rápido
python3 -m pytest tests/ --collect-only -q | tail -1
```

**Tests por módulo:**
- `test_backtest.py` — backtesting riguroso
- `test_dixon_coles.py` — Dixon-Coles
- `test_elo.py` — Elo Rating
- `test_ensemble.py` — ensemble lineal
- `test_features.py` — 28 features
- `test_heuristics.py` — 15 heurísticas
- `test_xg.py` — xG proxy (15 tests)
- `test_injuries_impact.py` — impacto lesiones
- `test_integration.py` — integración
- `test_multi_agent.py` — multi-agente simulado
- `test_orchestrator_live.py` — multi-agente LLM real
- `test_recalibration.py` — Platt scaling
- `test_referee_bias.py` — árbitro
- `test_shrinkage.py` — Elo shrinkage
- `test_stacking.py` — XGBoost stacking (NO adoptado)
- `test_threshold.py` — threshold mínimo confianza
- `test_weather.py` — weather Open-Meteo
- `test_composite_momentum.py` — composite momentum
- `test_mx_coefficients.py` — coeficientes MX
- `agents/` — multi-agente debate
