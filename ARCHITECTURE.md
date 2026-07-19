# 🏗️ Arquitectura — Predictions_MX

Documento vivo. Se actualiza conforme el sistema crece.

**Última actualización:** 2026-07-19 (Fase B.1 + multi-agente + cron jobs)

---

## Diagrama general (julio 2026)

```
┌─────────────────────────────────────────────────────────────────┐
│              FUENTES DE DATOS EXTERNAS                          │
├─────────────────────────────────────────────────────────────────┤
│  • SportMonks v3  → fixtures, lineups, stats, events, coaches   │
│  • ESPN API       → lesiones jugadores MX (Fase 10.5)           │
│  • Open-Meteo     → weather forecast próximos 7d                 │
│  • Odds (MVP)     → mercado sintético (Fase A.3, scraping TBD)  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS + rate limit 3k calls/h
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  sportmonks_client.py                            │
│  - Rate limiting (ventana móvil 1h)                              │
│  - Sistema de `includes` anidados (1 por call, v3 cambió semántica)│
│  - Paginación automática                                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼──────────────────────┐
        ▼                    ▼                      ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│   Ingesta    │   │   Ingesta ESPN   │   │   Ingesta ODDS   │
│  SportMonks  │   │   (lesiones)     │   │  (mercado MVP)   │
│              │   │                  │   │                  │
│  - fixtures  │   │                  │   │                  │
│  - lineups   │   │                  │   │                  │
│  - stats     │   │                  │   │                  │
│  - coaches   │   │                  │   │                  │
└──────┬───────┘   └────────┬─────────┘   └────────┬─────────┘
       │                    │                      │
       └────────────────────┼──────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  SQLite (data/predictions_mx.db)                │
│                  19 tablas (schema v2) — 272 MB                  │
│  fixtures, teams, seasons, players, coaches, events,             │
│  statistics, lineups, market_odds, player_injuries,              │
│  match_weather, analyst_predictions, ...                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Feature Engineering (28 features)               │
│  - Forma (exponential, recent, trend, consistency)                │
│  - Home/away split, H2H, season context                         │
│  - Altitud MX, rest days, fixture congestion                     │
│  - Coach tenure, referee bias, attendance ratio                  │
│  - Player injuries impact, travel distance                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              MODELO ENSEMBLE (xg + Elo + DC + heur)              │
│  Pesos calibrados Fase 8: xg=0.55 Elo=0.225 DC=0.135 heur=0.09  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              PLATT SCALING (Fase B.1) — calibración              │
│  1-vs-rest por clase, fit vía scipy.optimize L-BFGS-B            │
│  Coefs en data/platt_coefficients.json (re-fit lunes 09:00 UTC) │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              DECISIONES Y REPORTES                               │
│  - BD: home_win, draw, away_win, confidence, most_likely_score   │
│  - BD: features_used (JSON con ensemble + sub-modelos + score)   │
│  - Reconciliación: outcome_hit, score_hit, bts_hit, ou_2_5_hit   │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Reporte diario  │ │   Frontend   │ │  Multi-agente    │
│  (Telegram bot)  │ │  quinielas   │ │  debate (Fase 10)│
│                  │ │  .lol (web)  │ │  5 agentes + juez│
└──────────────────┘ └──────────────┘ └──────────────────┘
```

---

## Crons automatizados

| Frecuencia | Script | Mecanismo | Costo |
|---|---|---|---|
| `0 11 * * * UTC` | `full_pipeline.py` (10 pasos) | OpenClaw cron (me despierta) | ~5 min + tokens LLM |
| `0 4 * * * UTC` | `backup_db.sh` | crontab container | ~5s, 0 tokens |
| `0 9 * * 1 UTC` | `recalibrate_platt.sh` | crontab container | ~45s, 0 tokens |

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
- **Frontend quinielas.lol:** usa bind mount RO del mismo SQLite. Funciona porque solo lee.
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
- Migración a crontab container (2026-07-15): bash puro, 0 tokens, sin retry.
- Si falla: Telegram notification + exit 1.
- Mismo patrón aplicado para `recalibrate_platt.sh` (2026-07-19).

---

## Multi-agente debate (Fase 10)

Para predicciones críticas (final, liguilla), 5 sub-agentes LLM debaten en paralelo:

- 🐂 **Bull-Local** — argumentos a favor del local
- 🐻 **Bear-Visitante** — argumentos a favor del visitante
- 📊 **Numérico** — Predictions_MX ensemble (yo, ground truth cuantitativo)
- 🌐 **Contextual** — noticias recientes vía web_search (lesiones, alineaciones)
- 🔍 **Data Auditor** — valida integridad de features
- ⚖️ **Juez** — DWC-MAD (Dynamic Weighted Consensus)

**Restricción crítica (2026-06-27):** Plan MiniMax permite **3-4 agentes concurrentes**. Arquitectura ajustada para ese límite.

**Permisos:** agentes NO pueden modificar VPS / BD / archivos. Solo REPORTAN bugs y aportan argumentos cualitativos.

Ver `docs/ROADMAP.md` (sección Fase 10) y `memory/predictions_mx_multi_agent.md` para detalle.

---

## Estado actual (julio 2026)

✅ **Live en producción:**
- Sistema de predicciones con ensemble + Platt scaling
- Reporte diario Telegram 11:00 UTC
- Backups automáticos 04:00 UTC
- Recalibrador automático lunes 09:00 UTC
- [quinielas.lol](https://quinielas.lol) frontend LIVE (HTTPS, cert válido hasta 2026-09-25)
- Sistema de votos Sprint 4 (batch API, cookies HttpOnly)

🟡 **En desarrollo:**
- Recency weighting en fit Platt (Fase B.2)
- CLV tracker (cuando odds reales)
- Drift detection automático (Fase C)

📅 **Planeado:**
- Fase C (1 mes): autotrain, lesiones avanzadas
- Fase D (2-3 meses): tracking data, reports semanales

---

## Política de backups

- Backup diario 04:00 UTC vía `backup_db.sh` (crontab container)
- Retención: 3 backups más recientes en `data/backups/`
- BD bind mount RO para quinielas.lol frontend (no afecta writes)
- ⚠️ **Si container reinicia:** crond muere (PID 1 = openclaw). Re-lanzar manualmente:
  ```bash
  nohup crond -f -L /workspace/proyectos/data/logs/cron.log </dev/null &
  ```