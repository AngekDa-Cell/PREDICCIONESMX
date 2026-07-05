# Roadmap — Predictions_MX

> Plan de mejora continua del sistema de predicción.
> Última actualización: 2026-06-27 21:00 UTC (Fase 10.3 — sistema 5-agentes + quinielas.lol frontend LIVE en producción)

---

## 📊 Estado actual

**Métricas (backtest 2025, 340 partidos):**
- ✅ Accuracy: **52.65%** (vs 33.3% baseline)
- ✅ Brier Score: **0.5959**
- ✅ Calibration: <0.10 delta en todos los buckets
- ✅ Log Loss: 0.999

**Métricas (backtest 2024-2025, 680 partidos con xG + attendance heur):**
- ✅ Accuracy: **52.21%** (+3.97pp vs baseline sin xG)
- ✅ Brier Score: **0.6092** (-0.0112)

**Métricas (backtest 2025 aislado, 340 partidos):**
- ✅ Accuracy: **53.82%** (con heur attendance)
- ✅ Brier Score: **0.6005**

**Modelos:**
- Dixon-Coles (Poisson + τ)
- Elo Rating (FiveThirtyEight style, shrinkage 0.7)
- xG Proxy (Ridge log-link, decay 0.85)
- Ensemble: **xG 55% + Elo 22.5% + DC 13.5% + heur 9%** (Fase 8, grid search)

**Features:**
- **15 features engineered** (Fase 9 extendida)
- **15 heurísticas** (Fase 9 extendida)
- Narrativas manuales JSON

**Experimentos NO adoptados:**
- Stacking XGBoost (walk-forward 5 folds: Δ acc -0.65pp, Δ Brier -0.0031)

---

## ✅ Completado

### Fase 1: Schema + Migración + Scrape
- [x] Schema v2 (19 tablas)
- [x] Migración de v1 a v2
- [x] SportMonks scraping (250K+ records)
- [x] Venue enrichment (44/45 con altitud)

### Fase 2: Modelos base
- [x] Dixon-Coles Poisson
- [x] Elo Rating dinámico
- [x] **11 features engineered** (base, ahora 15 con Fase 9 extendida)
- [x] **11 heurísticas** (base, ahora 15 con Fase 9 extendida)
- [x] Narrativas editables
- [x] Bitácora del analista

### Fase 3: Calibración con datos MX
- [x] Altitud MX calibrada (regresión 1529 partidos)
- [x] Rest days calibrados
- [x] Fixture congestion calibrado
- [x] Forma ponderada exponencialmente

### Fase 4: Documentación
- [x] RESEARCH_SYNTHESIS.md (papers revisados)
- [x] METHODOLOGY.md (cómo funciona)
- [x] FEATURES.md (catálogo)
- [x] BACKTESTING_RESULTS.md (resultados empíricos)
- [x] src/predict/README.md (quick start)

### Fase 5: Backtesting riguroso
- [x] Backtest 2024-2025 (680 partidos)
- [x] Métricas: accuracy, Brier, Log Loss, calibration
- [x] Subgrupos: derby, confianza, fase de temporada
- [x] Detección de anomalías

---

## 🚧 En progreso (Fase 9)

### Mejoras completadas (Fases 6–8)
- [x] **Recalibración Platt scaling** — corregir overconfidence en >70% ✅
- [x] **Threshold mínimo de confianza** — no reportar si conf < 50% ✅ (+10pp accuracy)
- [x] **Backtest por equipo** — Cruz Azul y Pumas visitantes los más sobreestimados ✅
- [x] **Diagnóstico de drift Elo** — 16/18 equipos sobreestimados ✅
- [x] **Elo shrinkage global** — factor 0.7 calibrado con grid search ✅
- [x] **Elo shrinkage por equipo/localía** — experimental ✅
- [x] **Momentum compuesto** — combinar exponential form + recent form + trend + consistency ✅
- [x] **Weather desde Open-Meteo** — 1510 fixtures ingestados (93.4% cobertura) ✅
- [x] **xG Proxy (Fase 8)** — Ridge log-link, ensemble rebalanceado (+3.97pp acc) ✅
- [x] **Referee bias (Fase 9)** — 2,109 árbitros ingestados, feature + heurística #14 ✅ (Δ acc=0, valor cualitativo)
- [x] **Tests unitarios** — 186 tests pasando (~166s) ✅

### Pendiente Fase 9
- [x] **Attendance scraping** — ESPN API `mex.1/scoreboard?weeks=1-60` → 1,515/1,854 fixtures (81.7% global, 99.9% backtest 2024-2025) ✅
  - [x] Feature `get_attendance_ratio` agregada al feature set
  - [x] Heurística #15 attendance integrada (con hallazgo inverted: lleno favorece visitante)
  - [x] Backtest comparativo CON vs SIN heur: +0.29pp accuracy 2025 ✅
  - [x] Grid search pesos heur (9% baseline, 14/19/24%): empeoran, baseline óptimo ✅
- [ ] **Value bet detection automático** — comparar con cuotas de mercado cuando estén disponibles
- [x] **Stacking XGBoost** — meta-learner experimentado y validado (walk-forward 5 folds: Δ acc -0.65pp, Δ Brier -0.0031) ✅ **NO ADOPTADO** — ensemble lineal sigue óptimo con dataset actual
  - [x] XGBoost regularizado implementado (n_est=30, depth=2, reg_lambda=2)
  - [x] Logistic Regression fallback
  - [x] Walk-forward validation 5 folds
  - [x] Re-evaluar en ~2-3 temporadas (>2000 partidos)

### 🌐 Pendiente externo (no Liga MX)

- [ ] **quinielas.lol frontend** — Next.js para visualizar predicciones (PEDIDO 2026-06-27, esperando clarificación de Ángel sobre deploy/arquitectura)

---

## 🔮 Por hacer (Fase 10+)

### Fase 10: Ensemble avanzado

#### Stacking
- [ ] XGBoost sobre features del modelo
- [ ] Stacking: Poisson + XGBoost + heurísticas
- [ ] Voting ensemble con weights dinámicos

#### Referee profundo (Fase 9 ✅ base, falta profundidad)
- [x] Ingerir referee ID ✅
- [x] Calcular bias_score por árbitro ✅
- [x] Ajuste por referee conocido ✅
- [ ] Cards/fouls/penales por árbitro (cruzar con fixture_events)
- [ ] Player-level referee interaction (quién pitó a quién)

#### Passing networks (paper arXiv 2024)
- [ ] Construir passing networks por partido
- [ ] Métricas: clustering, betweenness, eigenvector centrality
- [ ] Combinar con match stats en ensemble

#### Half-time scoring (paper Springer 2024)
- [ ] Real-time features (goles al medio tiempo)
- [ ] Modelo dinámico con actualización
- [ ] Live tracking

### Fase 10: UX y deployment

#### Reportes Telegram
- [ ] Auto-reporte diario de partidos próximos
- [ ] Auto-update después de cada partido (bitácora)
- [ ] Notificación cuando modelo detecta anomalía
- [ ] Comparison con cuotas de mercado (cuando estén disponibles)

#### Web interface
- [ ] Dashboard con partidos del día
- [ ] Histórico de predicciones
- [ ] Accuracy tracker visual

---

## 📊 Métricas meta

| Métrica | Meta Fase 6 | Meta Fase 8 | Meta Fase 10 |
|---|---|---|---|
| Accuracy | >55% | >58% | >60% |
| Brier Score | <0.55 | <0.50 | <0.48 |
| Calibration delta | <0.05 | <0.03 | <0.02 |
| Log Loss | <0.95 | <0.90 | <0.85 |

**Nota:** Accuracy de 60% en fútbol es **excelente** (estado del arte). Más allá es muy difícil sin información privilegiada.

---

## 💡 Ideas en investigación

1. **Player embeddings** — vector representation de jugadores
2. **Graph neural networks** — sobre passing networks
3. **Temporal fusion** — transformer para series temporales de partidos
4. **Bayesian hierarchical models** — para team strength con incertidumbre
5. **Causal inference** — para identificar causas reales vs correlación

---

## 🎯 Prioridades inmediatas (próximas 2 semanas)

1. **Recalibrar Platt scaling** (auto)
2. **Ingerir attendance + referee** desde SportMonks
3. **Backtesting por equipo** (identificar dónde falla)
4. **Value bet detection** (cuando tengamos cuotas)
5. **Weather ingestion** desde Open-Meteo

---

## ⚠️ Anti-objetivos

Lo que **NO** vamos a hacer:
- ❌ Apostar dinero real sin entender los riesgos
- ❌ Pretender accuracy >65% (sería propaganda)
- ❌ Ignorar el factor suerte en fútbol
- ❌ Confiar ciegamente en el modelo sin revisión humana

---

## 📚 Referencias útiles

- Dixon & Coles (1997) — paper original
- McSharry (2007) — altitud
- FiveThirtyEight Soccer Predictions — Elo methodology
- MDPI 2025 review — features más usados
- PLOS One 2025 — psychology of sports

---

## 🌐 Proyecto paralelo: Frontend quinielas.lol (PENDIENTE)

**Pedido por Ángel 2026-06-27.** **No es parte de Fase 10** — es proyecto separado (visualización vs backend).

### Stack

- Next.js 14 (App Router) + Prisma + Tailwind + SQLite read-only
- Solo métodos GET
- BD: `predictions_mx.db` ya poblada

### Estado del sitio

- `quinielas.lol` → 144.126.133.221
- Puerto 80: empty reply (nginx caído)
- Puerto 443: TLS error (cert roto)
- **Requiere fix de nginx + certbot**

### Plan

- **Q1**: Setup base (Next.js + home/partido) — ✅ **COMPLETADO 2026-06-27**
- **Q2**: Equipo/calendario/modo oscuro — 🟡 **Pendiente** (4 páginas básicas funcionales)
- **Q3**: Deploy (nginx + certbot + container) — ✅ **COMPLETADO 2026-06-27** (https://quinielas.lol LIVE con cert Let's Encrypt)
- **Q4**: Integración con multi-agente — 🟡 **Pendiente**

### Preguntas resueltas (2026-06-27)

1. **¿Reactivar containers viejos?** NO. Ángel confirmó que `quiniela-frontend`/`quiniela-backend` viejos fueron dados de baja permanente. Container nuevo: `quiniela-frontend-new`.
2. **¿Dónde corre?** Container separado en red `back-predicciones_quiniela-net` (172.18.0.2).
3. **¿Arreglo nginx + certbot?** ✅ Hecho por Ángel: `certbot --nginx -d quinielas.lol -d www.quinielas.lol`.
4. **¿Prisma o better-sqlite3?** better-sqlite3 (Prisma incompatible con Alpine por libssl).
5. **¿Features adicionales?** Pendiente para Q2+ (modo oscuro, comparador, value bet).

### Estado del deploy (2026-06-27 22:40)

🟢 **LIVE en producción:**
- HTTPS con cert Let's Encrypt válido (hasta Sep 25)
- HTTP 200, sirviendo HTML real con partidos de Liga MX
- Container `quiniela-frontend-new` (Node 24.16.0-alpine)
- BD bind mount read-only desde `/opt/openclaw/volumes/Predictions_MX/workspace/proyectos/data`
- 4 rutas funcionales: `/`, `/partido/[id]`, `/equipo/[id]`, `/calendario`
- 6 headers de seguridad + validación regex contra SQL injection

Ver `memory/predictions_mx_frontend.md` para detalle completo.

---

## 🚧 Fase 10: Sistema Multi-Agente de Debate (2026-06-27)

**Decisión**: Ángel aprobó Opción C (sistema completo) el 2026-06-27.

### Motivación

Papers recientes (Du et al. 2023, TradingAgents 2024, DWC-MAD 2025) muestran que multi-agent debate puede mejorar razonamiento y reducir alucinaciones. Costo LLM无所谓 (Ángel tiene plan MiniMax ilimitado).

**⚠️ Restricción de concurrencia (Ángel 2026-06-27):** Plan MiniMax permite **3-4 agentes concurrentes**. Arquitectura ajustada:
- Fase 10.1: 3 agentes en paralelo (Bull, Bear, Numérico) + Juez
- Fase 10.2: 4 agentes en paralelo (Bull, Bear, Contextual, Auditor) + Juez

### Arquitectura

3-4 agentes + 1 juez + 1 orquestador (dependiendo de la fase):
- 🐂 **Bull-Local** — argumentos a favor del local
- 🐻 **Bear-Visitante** — argumentos a favor del visitante
- 📊 **Numérico** — Predictions_MX ensemble actual (yo)
- 🌐 **Contextual** — noticias recientes vía web_search (F10.2)
- 🔍 **Auditor Datos** — valida integridad antes de predecir (F10.2)
- ⚖️ **Juez** — pondera con Dynamic Weighted Consensus

### Restricciones duras

1. **Esperar a TODOS los agentes** antes de consolidar (no race conditions)
2. **Agentes NO pueden modificar VPS** — sin permisos `exec`/`write`/`gateway`
3. **Agentes REPORTAN bugs/datos legacy**, no los corrigen
4. **Auto-mejorable** — loop detección → reporte → fix (con OK de Ángel en casos complejos)
5. **Profesional** — logging estructurado, métricas, reportes

### Plan de implementación

- [x] **Fase 10.1 — Piloto Bull vs Bear** (1-2 días) — ✅ **COMPLETADO 2026-06-27** (modo simulate)
  - [x] Escribir prompts Bull-Local y Bear-Visitante ✅ `src/agents/prompts.py`
  - [x] Orquestador con DWC-MAD ✅ `src/agents/orchestrator.py` + `judge.py`
  - [x] Backtest 2025 (340 partidos, 0.49s) ✅ `data/multi_agent_pilot.json`
  - [x] Documentar resultados ✅ decisión: **GO_CONDITIONAL**
- [x] **Fase 10.2 — Validación con LLM real (parcial)** — ✅ IMPLEMENTADA 2026-06-27, validación lote en curso
  - [x] Implementar `orchestrate_live()` con `sessions_spawn` paralelo ✅ `orchestrator_live.py`
  - [x] Feature block inyectado a prompts ✅ `feature_block.py` (8 features)
  - [x] Parseo robusto de JSON desde outputs ✅ `extract_json_from_text()` con regex
  - [x] **14 tests nuevos** en `test_orchestrator_live.py` (5.46s)
  - [x] Demo v2 (Tigres-Puebla con features) ✅ `data/multi_agent_live_demo_v2.json`
  - [x] **Batch 1 (2 partidos)**: Debate 2/2 vs Num 1/2 → +50pp ✅
  - [x] **Batch 2 (2 partidos)**: Debate 1/2 vs Num 1/2 → 0pp ✅
  - [x] Acumulado 4 partidos: **Debate 75% vs Num 50% → +25pp** ✅
  - [x] **Bug seguridad detectado**: Bear_b1_p2 ejecutó queries SQLite (heredó workspace). Mitigado con restricciones explícitas en prompt.
  - [x] Workaround `sandbox: require` falló (no hay sandboxed runtime target configurado)
  - [ ] **Pendiente**: Batch 3-5 (6 partidos más → total 10) para validar significancia estadística
- [x] **Fase 10.3 — Sistema completo 5-agentes** — 🟡 EN PROGRESO 2026-06-27
  - [x] **Agente Contextual** ✅ `src/agents/contextual.py` — busca narrativas via web_search/web_fetch
  - [x] **Agente Data Auditor** ✅ `src/agents/data_auditor.py` — valida integridad, modo local sin LLM + modo LLM
  - [x] **Judge v2 (DWC-MAD)** ✅ `src/agents/judge.py` — soporta 5 agentes con pesos ajustados (numérico 0.45 base)
  - [x] **Aplicar qualitative_adjustment** del Contextual sobre probs finales
  - [x] **Aplicar penalización** del Data Auditor (abort → confidence *= 0.5)
  - [x] **2 tests nuevos** (5 agentes + auditor abort penalty). Total: **42 tests pasando** (5.55s)
  - [x] Auditor local validado en Tigres-Puebla (score 1.0, recommendation proceed)
  - [ ] **Pendiente**: Lanzar debate completo con 5 agentes en partidos reales (Batch 3)
  - [ ] **Pendiente (requiere OK Ángel)**: Configurar `agents.defaults.sandbox` para `sandbox: require` real
- [ ] **Fase 10.4 — Auto-mejora ongoing**
  - [ ] Loop detección → reporte → fix
  - [ ] Backlog priorizado
  - [ ] Reportes semanales

### Resultados Fase 10.2 validación lote (4 partidos, 2026-06-27)

**Setup:**
- 2 batches × 2 partidos = 4 partidos con sub-agentes LLM reales en paralelo
- 9 partidos pre-seleccionados con variedad (derby, home_fav, away_fav, picks difíciles, random)
- Tiempo por sub-agente: 24-45s (paralelo)
- Restricciones explícitas en prompt (`⚠️ NO SQL`, `⚠️ NO archivos`)

**Métricas:**
| | Numérico | Debate | Δ |
|---|---|---|---|
| Accuracy | 50% (2/4) | **75% (3/4)** | **+25pp** |
| Brier | 0.44 | 0.46 | +0.02 |

**Casos destacados:**
- ✅ **Querétaro-América (away_win)**: debate acertó, numérico falló. Bear detectó 5 features (forma, H2H 4-1, brecha plantilla 5x, split visitante invicto, Jardine consolidado) → juez cambió pick a away_win.
- ❌ **Pumas-SanLuis (away_win)**: ambos fallaron. Bull/Bear opuestos → numérico pesó 0.70 → juez heredó error del numérico.

**Conclusión preliminar:** Debate agrega valor cuando Bull o Bear detectan info contextual que el numérico no captura. Pierde valor cuando discrepan totalmente y heredan error.

### Resultados Fase 10.1 piloto (2026-06-27)

**Setup:**
- 3 archivos: permissions.py, prompts.py, judge.py (DWC-MAD), simulator.py, orchestrator.py
- 24 tests pasando (4.49s)
- Modo simulate (sin LLM) + modo live (Fase 10.2)

**Métricas backtest 2025 (340 partidos):**
- Ensemble numérico (baseline): 49.12% acc, Brier 0.6314
- Debate multi-agente + Juez: 49.12% acc (Δ 0pp), Brier 0.6335 (Δ +0.0021)
- 0 issues, 0 errores

**Decisión:** GO_CONDITIONAL → promover a Fase 10.2 con LLM real.

**Razonamiento:** El simulador heurístico (Bull/Bear con sesgo ±0.08) NO aporta señal nueva vs baseline. El algoritmo DWC-MAD funciona correctamente (no degrada), pero el valor del debate solo se puede validar con sub-agentes LLM que generen argumentos cualitativos reales.

### Tests (Fase 10.1)

- [x] `tests/test_multi_agent.py` — 24 tests pasando (4.49s):
  - Permisos respetados (7 tests)
  - Judge DWC-MAD básico + ajustes (5 tests)
  - AgentReport parsing + clamping (4 tests)
  - Simulator estructura (3 tests)
  - Orchestrator single + métricas (2 tests)
  - Prompts placeholders + DWC mention (3 tests)

### Archivos a crear

```
proyectos/src/agents/
├── orchestrator.py
├── bull_local.py
├── bear_visitante.py
├── contextual.py
├── data_auditor.py
├── judge.py
└── permissions.py

proyectos/data/
├── agent_reports/YYYY-MM-DD/
├── agent_metrics.json
└── backlog/improvements.md
```

### Métricas a trackear

- `predictions_total`, `bugs_detected_total`, `bugs_fixed_total`
- `avg_latency_sec`, `agent_agreement_rate`
- `agent_accuracy_by_role`, `numerico_vs_consensus_diff`
- `confidence_calibration`

### Documentación detallada

Ver `memory/predictions_mx_multi_agent.md` para:
- Arquitectura completa
- Permisos por agente (CRÍTICO)
- Algoritmo juez (DWC-MAD)
- Riesgos identificados (groupthink, latencia)
- Papers de respaldo
- Plan de tests

### Riesgos identificados

- **Groupthink**: instancias del mismo modelo comparten priors → mitigar con prompts opuestos
- **Latencia**: 6 agentes = minutos → paralelizar + timeouts
- **No convergencia**: debate en loop → máximo 3 rondas + juez final
- **Falsos positivos**: agentes reportan bugs que no son → yo valido antes de actuar

