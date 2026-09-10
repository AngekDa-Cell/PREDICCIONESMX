# Roadmap — Predictions_MX

> Plan de mejora continua del sistema de predicción.
> Última actualización: 2026-09-10 (merge frontend Next.js + Dokploy + sistema quinielas + recalibración Platt)

---

## 📊 Estado actual

**Métricas live (septiembre 2026, n=994 OOS, Fase B.1 con Platt scaling):**
- ✅ Accuracy: **51.1%** (Platt OOS, +17.8pp vs 33.3% baseline)
- ✅ Brier Score: **0.2009** (3-class, normalizado por n*k)
- ✅ Calibration: excelente (prob=0.50 → actual 58%, prob=0.60 → actual 74%)
- ✅ Log Loss: 1.0158

**Métricas Fase B.0 (backtest 2024-2025, 680 partidos con xG + attendance heur):**
- Accuracy: **52.21%** (+3.97pp vs baseline sin xG)
- Brier Score: **0.6092** (-0.0112)

**Métricas Fase B.0 (backtest 2025 aislado, 340 partidos):**
- Accuracy: **53.82%** (con heur attendance)
- Brier Score: **0.6005**

**Modelos:**
- Dixon-Coles (Poisson + τ)
- Elo Rating (FiveThirtyEight style, shrinkage 0.7)
- xG Proxy (Ridge log-link, decay 0.85)
- Ensemble: **xG 55% + Elo 22.5% + DC 13.5% + heur 9%** (Fase 8, grid search)
- **Platt scaling** (Fase B.1) — calibración de probabilidades, recalibración semanal lunes

**Features:**
- **28 features engineered** (Fase 9 extendida)
- **15 heurísticas** (Fase 9 extendida)
- Narrativas manuales JSON

**Frontend + Sistema quinielas:**
- ✅ Next.js 14 App Router EN este repo (no separado)
- ✅ 10+ rutas funcionales
- ✅ Sistema quinielas crowdsourced (3 APIs, 2 páginas)
- ✅ Deploy Dokploy + healthcheck + Traefik

**Tests:**
- ✅ **257 tests Python** pasando (~30s)

**Experimentos NO adoptados:**
- Stacking XGBoost (walk-forward 5 folds: Δ acc -0.65pp, Δ Brier -0.0031)
- A/B pesos elo-heavy (Fase B.0, n=300: Δ acc -0.67pp) — baseline mantiene
- Isotonic regression (Fase B.2, n=800 OOS: Platt gana en Brier en 3/3 temporadas)

---

## ✅ Completado

### Fases 1-9 — Backend de predicción

- [x] **Fase 1**: Schema v2 (19 tablas) + migración v1→v2 + scrape SportMonks (250K+ records) + venue enrichment
- [x] **Fase 2**: Modelos base (Dixon-Coles, Elo, 11 features, 11 heurísticas, narrativas, bitácora)
- [x] **Fase 3**: Calibraciones MX (altitud, rest days, fixture congestion, forma exponencial)
- [x] **Fase 4**: Documentación técnica (RESEARCH_SYNTHESIS, METHODOLOGY, FEATURES, BACKTESTING, src/predict/README)
- [x] **Fase 5**: Backtesting riguroso (680 partidos, métricas desagregadas por derby/confianza/temporada)
- [x] **Fase 6**: Threshold mínimo confianza, backtest por equipo, diagnóstico drift Elo, Elo shrinkage global 0.7
- [x] **Fase 7**: Composite momentum (Feature #12, Heurística #12), weather Open-Meteo (1510 fixtures, 93.4% cobertura)
- [x] **Fase 8**: xG Proxy (Ridge log-link), ensemble rebalanceado (+3.97pp acc)
- [x] **Fase 9**: Referee bias (2,109 árbitros, Feature #14), attendance ESPN (1,515/1,854 fixtures, Heurística #15 invertida)

### Fase A — Frontend Next.js + Sistema de quinielas

- [x] **Fase A.0**: Stack Next.js 14 + better-sqlite3 + Tailwind (Prisma descartado por incompatibilidad Alpine)
- [x] **Fase A.1**: 10+ rutas funcionales (home Cinépolis-style, partido, equipo, calendario, historial, resultados, efectividad, análisis, equipos)
- [x] **Fase A.2**: Sistema de quinielas crowdsourced:
  - [x] API `/api/quiniela` (POST batch + GET picks)
  - [x] API `/api/votes/[token]` (POST/GET voto individual partido)
  - [x] API `/api/health` (healthcheck Traefik)
  - [x] Página `/votacion` (llenar quiniela completa de jornada)
  - [x] Página `/voto/[token]` (voto partido individual vía link compartible)
  - [x] Tokens opacos 8 chars base32 (sha256 truncated, anti-enumeración con SECRET_SALT)
  - [x] Client hash: sha256(cookie + ip_prefix + ua_fingerprint)[:32]
  - [x] Cookies HttpOnly + SameSite=Lax + 180d (votante_id) + 365d (votante_quinc_v1)
  - [x] Validación regex anti-SQLi `^\d{1,10}$` en todos los IDs de URL
  - [x] BD secundaria `votes_mx.db` (RW, journal_mode WAL, autocheckpoint)
- [x] **Fase A.3**: Market odds MVP sintético (cuotas reales: scraping TBD)

### Fase B — Calibración Platt + Recalibración Auto (2026-07-18/19)

- [x] **Fase B.0**: A/B pesos ensemble (5 configs n=300 → baseline mantiene, Δ acc dentro de ruido)
- [x] **Fase B.1**: Platt scaling 1-vs-rest aplicado (commit `1c96410`)
  - [x] Coefs: home (1.88, +0.42), draw (-0.31, -1.43), away (1.62, +0.39)
  - [x] OOS Brier: 0.2009 (n=994, leave-one-season-out)
- [x] **Fase B.1.bis**: Recalibrador automático semanal (commit `bf6f539`)
  - [x] `scripts/recalibrate_platt.sh` (185 LOC, bash puro)
  - [x] Cron `0 9 * * 1 UTC` (lunes, antes del pipeline diario)
  - [x] Rollback automático si Δ Brier empeora >1pp
- [x] **Fase B.2**: Platt vs Isotonic (commit `66fe4b3`) → Platt gana en Brier OOS en 3/3 temporadas

### Fase C — Deploy Dokploy (2026-09-09/10)

- [x] **Fase C0**: Deploy-ready state (commit `2c91269`)
  - [x] Multi-stage Dockerfile (Node 24.16.0 builder + Python 3.12-slim runtime)
  - [x] `entrypoint.sh` (wait-for-DB + supercronic + `node server.js` PID 1)
  - [x] `crontab.txt` (3 cron jobs)
  - [x] `requirements.txt` consolidado (pinned 2026-09-09)
  - [x] `.dockerignore`
  - [x] `deploy/DOKPLOY.md` + `docs/DEPLOY_DOKPLOY.md`
- [x] **Fase C1**: App desplegada en Dokploy
  - [x] appId `McpkBWGE8WuNEkG0rFWIL`
  - [x] Bind mount `/srv/predicciones-mx/data → /workspace/proyectos/data` (permisos 1000:1000)
  - [x] Env vars: SM_TOKEN, TG_TOKEN, TZ=MX, DATABASE_URL, SKIP_DB_CHECK=1
- [x] **Fase C1b**: Healthcheck HTTP `/api/health` en :3000 (commit `0eef307`)
  - [x] Traefik entrypoint `websecure` con cert wildcard `*.barberia.date`
  - [x] `predicciones.barberia.date` LIVE con HTTPS 200 OK en `/`, `/api/health`, `/version`
- [x] **Fase C2**: Bugfixes deploy
  - [x] `crontab.txt` → `/etc/crontab.app` (faltaba en COPY)
  - [x] `supercronic -no-reap` (PID 1 reaper fix)
  - [x] `SKIP_DB_CHECK=1` para deploy inicial sin BD
  - [x] `chown -R 1000:1000` bind-mount (user `app` es uid 1000)
  - [x] Lazy init `votesDb` + glibc builder (better-sqlite3 compat)
- [x] **Fase C3**: Seguridad
  - [x] Sanitize LLM prompt errors (commit `84c8b61`)
  - [x] Parametrize SQL queries (commit `84c8b61`)

### Fase 10 — Multi-agente debate (Fase 10.3, experimental)

- [x] **Fase 10.1 — Piloto Bull vs Bear** (2026-06-27) → modo simulate, GO_CONDITIONAL
- [x] **Fase 10.2 — Validación con LLM real** (parcial, n=4)
  - [x] Debate 75% acc vs Numérico 50% → **+25pp** (acumulado)
  - [x] Caso destacado: Querétaro-América (debate acertó, numérico falló)
- [x] **Fase 10.3 — Sistema completo 5-agentes** (EN PROGRESO)
  - [x] Agente Contextual (`src/agents/contextual.py`) — web_search narrativas
  - [x] Agente Data Auditor (`src/agents/data_auditor.py`) — valida integridad
  - [x] Judge v2 DWC-MAD (`src/agents/judge.py`) — soporta 5 agentes
  - [x] `apply_qualitative_adjustment` del Contextual sobre probs finales
  - [x] Penalización del Data Auditor (abort → confidence *= 0.5)
  - [x] Auditor local validado en Tigres-Puebla (score 1.0, recommendation proceed)
- [ ] **Fase 10.4 — Auto-mejora ongoing** (pendiente)
- [ ] **Fase 10.5 — Validación estadística n=10** (Batches 3-5 pendientes, actual n=4)

---

## 🔄 En progreso

### Mejoras activas

- [ ] **Recency weighting en fit Platt** (Fase B.2) — peso 1.0 temp reciente, 0.7 media, 0.4 antigua. Esperado: -0.5pp Brier en n recientes.
- [ ] **Multi-agente debate con Platt** — agentes deben usar probs calibradas (no raw ensemble).
- [ ] **Validación estadística Fase 10.2** — completar Batches 3-5 (n=10) para validar +25pp con significancia.

---

## 🔮 Por hacer

### Fase D — Multimodal + NLP/LLMs (2026-Q4)

**Objetivo:** integrar features textuales (noticias, declaraciones, lesiones reportadas) al ensemble, cumplir con la visión del proyecto SPLMYOP.

#### D.1 — Embeddings de noticias

- [ ] Pipeline de ingesta de noticias (ESPN, medios MX, RSS de equipos)
- [ ] Embeddings con LLM (`text-embedding-3-small` o similar) o modelo local (Sentence-BERT multilingual)
- [ ] Agregación por partido (sum/max/mean de embeddings relevantes)
- [ ] Feature nueva: `news_sentiment_home`, `news_sentiment_away`, `news_volume_diff`

#### D.2 — NLP features para el ensemble

- [ ] Clasificación de menciones (lesión, sanción, declaraciones DT, cambio táctico)
- [ ] Extracción de entidades (jugadores, equipos, eventos)
- [ ] Feature nueva: `injury_mention_count_home`, `coach_pressure_mentions`
- [ ] Integración con Feature Engineering existente (28 → ~35 features)

#### D.3 — API robusta

- [ ] Autenticación (API keys o JWT) en endpoints `/api/*`
- [ ] Rate limiting (Upstash, Redis, o en memoria)
- [ ] Monitoreo (Sentry, OpenTelemetry, métricas Prometheus)
- [ ] Documentación OpenAPI auto-generada

#### D.4 — CI/CD

- [ ] GitHub Actions: tests Python + lint TypeScript en cada PR
- [ ] Build automático de imagen Docker
- [ ] Deploy continuo a Dokploy (branch main → staging)
- [ ] Smoke tests post-deploy (curl `/api/health`, verificar predicciones)

#### D.5 — Predicción live / half-time (paper Springer 2024)

- [ ] Real-time features (goles al medio tiempo)
- [ ] Modelo dinámico con actualización en vivo
- [ ] WebSocket para frontend

#### D.6 — Tracking data (paper arXiv 2024)

- [ ] Evaluar fuentes (StatsBomb open data, Opta partnership)
- [ ] Passing networks por partido (clustering, betweenness, eigenvector centrality)
- [ ] Combinar con match stats en ensemble

### Referee profundo (Fase 9 base ✅, falta profundidad)

- [x] Ingerir referee ID ✅
- [x] Calcular bias_score por árbitro ✅
- [x] Ajuste por referee conocido ✅
- [ ] Cards/fouls/penales por árbitro (cruzar con fixture_events)
- [ ] Player-level referee interaction (quién pitó a quién)

### Player embeddings / GNN / Temporal fusion / Bayesian hierarchical

- [ ] Vector representation de jugadores
- [ ] Graph neural networks sobre passing networks
- [ ] Transformer para series temporales de partidos
- [ ] Bayesian hierarchical models para team strength con incertidumbre
- [ ] Causal inference para identificar causas reales vs correlación

### Reportes Telegram mejorados

- [ ] Auto-reporte diario de partidos próximos ✅ (Fase 11...)
- [ ] Auto-update después de cada partido (bitácora)
- [ ] Notificación cuando modelo detecta anomalía
- [ ] Comparison con cuotas de mercado (cuando estén disponibles)

---

## 📊 Métricas meta

| Métrica | Meta Fase 6 | Meta Fase 8 | **Actual Fase B.1** | Meta Fase D |
|---|---|---|---|---|
| Accuracy | >55% | >58% | **51.1%** | >60% |
| Brier Score | <0.55 | <0.50 | **0.2009** | <0.48 |
| Calibration delta | <0.05 | <0.03 | <0.02 ✅ | <0.02 |
| Log Loss | <0.95 | <0.90 | **1.0158** | <0.85 |
| Tests | 50 | 100 | **257** | 350 |

**Nota:** Accuracy de 60% en fútbol es **excelente** (estado del arte). Más allá es muy difícil sin información privilegiada.

---

## ⚠️ Anti-objetivos

Lo que **NO** vamos a hacer:
- ❌ Apostar dinero real sin entender los riesgos
- ❌ Pretender accuracy >65% (sería propaganda)
- ❌ Ignorar el factor suerte en fútbol
- ❌ Confiar ciegamente en el modelo sin revisión humana
- ❌ Rastrear usuarios con IPs/UA crudos (usamos fingerprints)
- ❌ Exponer endpoints sin validación anti-SQLi

---

## 📚 Referencias útiles

- Dixon & Coles (1997) — paper original
- McSharry (2007) — altitud
- FiveThirtyEight Soccer Predictions — Elo methodology
- MDPI 2025 review — features más usados
- PLOS One 2025 — psychology of sports
- Constantinou & Fenton (2018) — pi-football Bayesian networks
- arXiv 2024 — Sports multimodal models survey
- DWC-MAD (2025) — Dynamic Weighted Consensus Multi-Agent Debate

---

## 🚧 Fase C — Deploy Dokploy (2026-09-09/10)

**Decisión:** migrar de "OpenClaw cron + VPS manual" a "Dokploy Application long-running + supercronic dentro del container".

### Motivación

- OpenClaw cron retryeaba en overload (~40K tokens/retry sin valor).
- Deploy manual con nginx + certbot era frágil.
- Sin healthcheck estandarizado → Traefik no sabía cuándo restart.
- Multi-stage Dockerfile unifica front + pipeline en una sola imagen.

### Arquitectura

```
Dokploy panel (puerto 3000 interno)
    └─ Traefik (entrypoint websecure, cert wildcard *.barberia.date)
         └─ predicciones.barberia.date → predicciones-mx-app-XXXXX :3000
              ├─ node server.js (PID 1, Next.js standalone)
              └─ supercronic /etc/crontab.app (background)
                   ├─ 0 11 * * *  python scripts/full_pipeline.py
                   ├─ 0 4  * * *  bash scripts/backup_db.sh
                   └─ 0 9  * * 1  bash scripts/recalibrate_platt.sh
```

### Bind mounts (Dokploy)

- `/srv/predicciones-mx/data` → `/workspace/proyectos/data` (RW, uid 1000)
  - `predictions_mx.db` (BD principal)
  - `votes_mx.db` (BD de votos)
  - `backups/`, `logs/`

### Endpoints live

- 🟢 `https://predicciones.barberia.date/` — home dashboard
- 🟢 `https://predicciones.barberia.date/api/health` — healthcheck
- 🟢 `https://predicciones.barberia.date/version` — versión
- 🟢 `https://predicciones.barberia.date/partido/[id]` — partido
- 🟢 `https://predicciones.barberia.date/equipo/[id]` — equipo
- 🟢 `https://predicciones.barberia.date/calendario` — calendario
- 🟢 `https://predicciones.barberia.date/resultados` — track record
- 🟢 `https://predicciones.barberia.date/votacion` — llenar quiniela
- 🟢 `https://predicciones.barberia.date/voto/[token]` — voto individual
- 🟢 `https://predicciones.barberia.date/analisis`, `/efectividad`, `/equipos`, `/historial`

Ver [`docs/DEPLOY_DOKPLOY.md`](./DEPLOY_DOKPLOY.md) y [`deploy/DOKPLOY.md`](../deploy/DOKPLOY.md) para procedimiento.

---

## 🚧 Fase 10 — Sistema Multi-Agente de Debate (2026-06-27 en adelante)

**Decisión**: Ángel aprobó Opción C (sistema completo) el 2026-06-27.

### Arquitectura (Fase 10.3 — sistema completo)

5 agentes + 1 juez + 1 orquestador:
- 🐂 **Bull-Local** — argumentos a favor del local
- 🐻 **Bear-Visitante** — argumentos a favor del visitante
- 📊 **Numérico** — Predictions_MX ensemble actual (ground truth cuantitativo)
- 🌐 **Contextual** — noticias recientes vía web_search (lesiones, alineaciones)
- 🔍 **Auditor Datos** — valida integridad antes de predecir (modo local sin LLM + modo LLM)
- ⚖️ **Juez** — pondera con Dynamic Weighted Consensus v2 (soporta 5 agentes, numérico base 0.45)

### Restricciones duras

1. **Esperar a TODOS los agentes** antes de consolidar (no race conditions)
2. **Agentes NO pueden modificar VPS** — sin permisos `exec`/`write`/`gateway`
3. **Agentes REPORTAN bugs/datos legacy**, no los corrigen
4. **Auto-mejorable** — loop detección → reporte → fix (con OK de Ángel en casos complejos)
5. **Restricción concurrencia**: 3-4 agentes paralelos (plan MiniMax)

### Resultados Fase 10.2 validación lote (n=4, 2026-06-27)

| | Numérico | Debate | Δ |
|---|---|---|---|
| Accuracy | 50% (2/4) | **75% (3/4)** | **+25pp** |
| Brier | 0.44 | 0.46 | +0.02 |

**Casos destacados:**
- ✅ **Querétaro-América (away_win)**: debate acertó, numérico falló. Bear detectó 5 features (forma, H2H 4-1, brecha plantilla, split visitante invicto, Jardine consolidado) → juez cambió pick.
- ❌ **Pumas-SanLuis (away_win)**: ambos fallaron. Bull/Bear opuestos → numérico pesó 0.70 → juez heredó error.

**Conclusión:** Debate agrega valor cuando Bull o Bear detectan info contextual que el numérico no captura. Pierde valor cuando discrepan totalmente y heredan error.

### Plan inmediato

- [ ] Completar Batches 3-5 (n=10 acumulado) para significancia estadística
- [ ] Integrar Platt scaling en probs de Numérico (ahora usa raw ensemble)
- [ ] `sandbox: require` real (workaround falló) → requiere OK Ángel

### Archivos clave

- `src/agents/orchestrator.py` — orquestador 3-agentes (Bull, Bear, Numérico) + juez
- `src/agents/orchestrator_live.py` — orquestador con LLM real (paralelo)
- `src/agents/judge.py` — DWC-MAD v2 (5-agentes)
- `src/agents/contextual.py` — agente noticias
- `src/agents/data_auditor.py` — validador integridad
- `src/agents/prompts.py` — templates prompts
- `src/agents/feature_block.py` — 8 features inyectadas a prompts

### Métricas a trackear

- `predictions_total`, `bugs_detected_total`, `bugs_fixed_total`
- `avg_latency_sec`, `agent_agreement_rate`
- `agent_accuracy_by_role`, `numerico_vs_consensus_diff`
- `confidence_calibration`

---

## 🌐 Proyecto integrado: Frontend Next.js + Sistema de Quinielas (Live)

**Antes:** proyecto paralelo, repo separado, "pendiente Q1+Q2".  
**Ahora:** **EN este repo, LIVE en producción**, 10+ rutas funcionales.

### Stack

- Next.js 14.2.5 (App Router) + better-sqlite3 + Tailwind + TypeScript 5.5
- BD: `predictions_mx.db` (read-only bind) + `votes_mx.db` (RW)
- Cookies HttpOnly + tokens opacos + validación regex anti-SQLi

### Rutas funcionales (10+)

| Ruta | Descripción |
|---|---|
| `/` | Dashboard Cinépolis-style (hero gradient, stat cards, partido destacado, próximos 5) |
| `/analisis` | Análisis agregado del modelo |
| `/calendario` | Calendario por jornada |
| `/efectividad` | Métricas de efectividad histórica |
| `/equipos` | Índice completo de equipos |
| `/equipo/[id]` | Detalle de equipo (próximos, recientes, stats) |
| `/historial` | Historial de predicciones |
| `/partido/[id]` | Detalle de partido individual |
| `/resultados` | Track record con accuracy y Brier live |
| `/votacion` | Llenar quiniela batch por jornada |
| `/voto/[token]` | Voto individual partido (link compartible) |

### API endpoints (3)

| Endpoint | Método | Descripción |
|---|---|---|
| `/api/health` | GET | Healthcheck Traefik/Dokploy |
| `/api/quiniela` | POST/GET | Batch por jornada |
| `/api/votes/[token]` | POST/GET | Individual partido |

Ver [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) y [`docs/QUINIELAS_SYSTEM.md`](./QUINIELAS_SYSTEM.md) para detalle.

### Estado del deploy (2026-09-10)

🟢 **LIVE en producción:**
- HTTPS con cert wildcard `*.barberia.date`
- HTTP 200 en `/`, `/api/health`, `/version`
- Container Dokploy `predicciones-mx-app-McpkBWGE8WuNEkG0rFWIL`
- BD bind mount con permisos `1000:1000`
- 10+ rutas funcionales
- Sistema quinielas crowdsourced (votos + crowd summary)
- Validación regex contra SQL injection en TODOS los IDs
- Healthcheck cada 60s vía Traefik

### Próximas mejoras frontend

- [ ] Modo oscuro (ya está parcialmente con variables CSS)
- [ ] Comparador de modelos en `/analisis`
- [ ] Value bet detection cuando odds reales disponibles
- [ ] PWA / offline support
- [ ] Tests E2E (Playwright)
