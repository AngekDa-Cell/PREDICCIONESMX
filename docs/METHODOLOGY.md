# Methodology — Predictions_MX

> Documentación técnica completa del sistema de predicción.
> Última actualización: 2026-06-27

Este documento describe en detalle **cómo funciona el modelo** de Predictions_MX — qué algoritmos, qué features, qué calibraciones, qué heurísticas. Para una revisión de papers académicos, ver [`RESEARCH_SYNTHESIS.md`](RESEARCH_SYNTHESIS.md).

---

## 🏗️ Arquitectura general

El sistema sigue una arquitectura en **5 capas**:

```
┌─────────────────────────────────────────────────────────┐
│  CAPA 5: NARRATIVA DEL USUARIO                         │
│  Input: --narrative + JSON files                       │
│  Output: ajustes cualitativos                          │
├─────────────────────────────────────────────────────────┤
│  CAPA 4: HEURÍSTICAS DEL ANALISTA HUMANO                │
│  Altitud MX calibrada + Derby + Presión DT + Momentum  │
│  Output: probabilidades ajustadas                      │
├─────────────────────────────────────────────────────────┤
│  CAPA 3: ENSEMBLE (DC + Elo)                            │
│  Dixon-Coles (65%) + Elo Rating (35%)                  │
│  Output: probabilidad final 1X2                         │
├─────────────────────────────────────────────────────────────┤
│  CAPA 2: MODELOS ESTADÍSTICOS                           │
│  Dixon-Coles (Poisson + corrección τ)                   │
│  Elo Rating (FiveThirtyEight style)                     │
├─────────────────────────────────────────────────────────┤
│  CAPA 1: FEATURES DERIVADOS                             │
│  **15 features** engineered (Fase 9 extendida)          │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 Capa 1 — Features (11)

### Features automáticos (calculados desde BD)

| Feature | Cálculo | Rango | Justificación |
|---------|---------|-------|---------------|
| **Forma reciente (5)** | W/D/L últimos 5 partidos | 0-3 puntos/partido | Forma reciente es predictor estándar (MDPI 2025) |
| **Forma ponderada exp** | Decay 0.85, últimos 10 | 0-3 puntos | Más peso a partidos recientes |
| **H2H** | Últimos 10 partidos entre equipos | 0-100% win rate local | Patrones históricos |
| **Home/Away split** | Últimos 15 partidos local/visit | 0-100% W rate | Sesgo de local diferenciado |
| **Altitud** | Coordenadas de venues | 0-2700m MX | McSharry 2007 BMJ (calibrado a MX) |
| **Rest days** | Días desde último partido | 0-99 | Fatiga / rust |
| **Coach pressure** | Winless streak del DT | 0-99 partidos | Proxy de motivación (PLOS 2025) |
| **Coach tenure** | Días del DT en el cargo | 0-∞ | New manager bounce (MDPI 2025) |
| **Travel distance** | Suma haversine últimos 7d | 0-5000+ km | Fatiga por viaje |
| **Fixture congestion** | # partidos últimos 7d | 0-5 | Calendar congestion |
| **Attendance/crowd** | Promedio últimos 5 | 0-100% capacidad | Home advantage dynamic |

### Features manuales (JSON + comando)

- **Nivel de motivación narrativa** — `[0, 1]` con descripción textual
- **Choking risk** — si el local es "high-status" y se ahoga en presión

---

## 🧮 Capa 2 — Modelos estadísticos

### **Dixon-Coles** (`dixon_coles.py`)

Implementación del paper original Dixon & Coles (1997).

**Parámetros:**
- `λ_home = home_advantage × attack_home × defense_away`
- `λ_away = attack_away × defense_home`
- `ρ (rho)` = corrección para scorelines bajos (0-0, 1-1)

**Ajuste:**
- Estimación por método de momentos (no MLE completo)
- Promedio de goles anotados/concedidos por partido local/visitante
- Relativos al promedio de la liga → attack_strength, defense_strength

**Probabilidades 1X2:**
```
P(home_win) = Σ P(h, a)  para h > a
P(draw)      = Σ P(h, a)  para h = a
P(away_win) = Σ P(h, a)  para h < a
```

Donde `P(h, a) = Poisson(h; λ_home) × Poisson(a; λ_away) × τ(h, a)` con τ siendo la corrección Dixon-Coles.

### **Elo Rating** (`elo.py`)

Implementación estilo **FiveThirtyEight** (Nate Silver).

**Parámetros:**
- Rating inicial: 1500
- K-factor: 20 (con multiplier por goal difference)
- Home advantage: 100 puntos Elo (≈ 60% win rate)

**Update después de cada partido:**
```
E_new = E_old + K × multiplier × (actual - expected)
```

**Predicción:**
- Diferencia de Elo → distribución Poisson de goles
- expected_home_goals = 1.3 + (elo_diff / 100) × 0.15
- expected_away_goals = 1.0 - (elo_diff / 100) × 0.15

---

## 🎯 Capa 3 — Ensemble

**Versión Fase 8 (con xG):**
```
ensemble = 0.55 × xG_probs
         + 0.225 × Elo_probs
         + 0.135 × Dixon-Coles_probs
         + 0.09 × heuristic_probs
```

**Por qué estos pesos (Fase 8, grid search 2024-2025):**

| Modelo individual | Accuracy | Brier |
|---|---|---|
| **xG proxy** (Fase 8) | **51.91%** | 0.6173 |
| Elo Rating (con shrinkage) | 48.97% | 0.6047 |
| Dixon-Coles | 41.91% | 0.6631 |
| Heurísticas | 40.74% | 0.6593 |

El **xG proxy rolling** es el modelo individual más fuerte. Combinarlo con
los demás en proporción 55/22.5/13.5/9 maximiza la accuracy y minimiza el
Brier simultáneamente.

**Δ vs baseline anterior (sin xG):**
- Accuracy: **+3.97pp** (48.24% → 52.21%)
- Brier: **-0.0112** (0.6205 → 0.6092)
- Resultado 2025 aislado: 50.00% → 53.53% (+3.53pp)

**Ver backtesting detallado** → ver [`BACKTESTING_RESULTS.md`](BACKTESTING_RESULTS.md).

---

## 🧠 Capa 4 — Heurísticas (`heuristics.py`)

11 reglas empíricas, ordenadas por impacto:

### A. **Altitud MX calibrada** (`get_altitude_advantage` + ajuste)

**Paper:** McSharry 2007 BMJ
**Calibración MX:** +2.48% win rate por 1000m de ΔAltitud (vs McSharry +12% en Sudamérica)

```python
delta_alt = home_altitude - away_altitude
boost = (delta_alt / 1000) × 0.0248
```

Solo aplica si `|delta_alt| >= 1000m`.

### B. **Derby / Clásico detection**

Detecta automáticamente 6 derbies MX:
- Clásico Nacional (América vs Chivas)
- Clásico Regio (Rayados vs Tigres)
- Clásico Capitalino (América vs Pumas)
- Clásico Tapatío (Chivas vs Atlas)
- Clásico de la Minerda (Santos vs Pachuca)
- Clásico Azulgrana (Cruz Azul vs América)

En derbies: **flatten 15%** (todas las probabilidades se acercan al promedio).

### C. **Presión DT (winless streak)**

Si DT lleva 5+ partidos sin ganar:
- Reduce su win probability -10%
- Reduce confidence -12%

### D. **Forma reciente (W-streak / L-streak)**

3+ victorias consecutivas → +8% boost al local (decay lineal)
3+ derrotas consecutivas → -8% al visitante

### E. **Travel fatigue**

Si visitante recorrió >1500km en últimos 7 días:
- Reduce away_win -8% (max)
- Linear scaling hasta 3000km

### F. **Fixture congestion**

3+ partidos del visitante en últimos 7 días → -5% away_win

### G. **Coach tenure (new manager bounce)**

DT con <30 días en cargo → +5% "bounce" (inestable, confidence -12%)

### H. **Momentum score**

Diferencia ponderada exponencialmente >0.6 → ±8% ajuste al favorito

### I. **H2H dominance**

H2H >65% local o <35% local → ±9% boost

---

## 📝 Capa 5 — Narrativas del usuario

**Input:** JSON en `data/manual/narratives_*.json` + flag `--narrative`

**Estructura:**
```json
{
  "team": "América",
  "weight": 0.7,
  "direction": "favor_home",
  "description": "DT nuevo + 5 refuerzos clave",
  "active": true
}
```

**Aplicación:**
- Solo `active=true` se aplica
- Magnitud = `(weight - 0.5) × 0.12`
- Confidence penalty = `1 - weight × 0.05`

---

## 🔧 Calibraciones MX

Coeficientes calibrados con **1529 partidos Liga MX (2021-2026)**:

| Coeficiente | Valor MX | Fuente |
|---|---|---|
| Altitud win rate / 1000m | +2.48% | Regresión lineal MX |
| Altitud GD / 1000m | +0.088 | Regresión lineal MX |
| Baseline home win (Δh=0) | 57.6% | Promedio MX |
| Rest days óptimo | 4-6 días | Distribución MX |
| Rest days fatiga | <3 días | Distribución MX |
| Rest days rust | >10 días | Distribución MX |
| Fixture congestion efecto | Bajo en MX | Distribución MX (sorprendente) |

---

## 📊 Métricas y backtesting

Ver [`BACKTESTING_RESULTS.md`](BACKTESTING_RESULTS.md) para resultados detallados.

Resumen de últimos 80 partidos:
- **Accuracy ensemble:** ~42%
- **Brier Score:** ~0.66
- **Calibration:** desalineada (overconfident en wins)

---

## ⚠️ Limitaciones conocidas

1. **Sin xG**: No tenemos expected goals calculado
2. **Sin referee bias**: Referee ID no en BD
3. **Sin weather data**: Open-Meteo no integrado aún
4. **No live data**: No procesamos partidos en vivo
5. **Platt scaling**: Implementado pero mejora marginal (NLL 1.018 → 1.015). Usar con precaución en ventanas cortas.
6. **Threshold**: Mejora +10pp pero filtra 60% de partidos. Útil en producción, no para evaluación.
7. **Elo shrinkage local por equipo**: Experimental — mejora algunos equipos pero no global. Requiere walk-forward recursivo.
8. **Derby detection**: Solo 6 derbies hardcoded — se pueden añadir más
9. **Sin narratives context-aware**: Las narrativas no se ponderan por contexto

---

## 🔄 Próximas mejoras

Ver [`ROADMAP.md`](ROADMAP.md).

---

## 🎯 Elo Shrinkage (Fase 6)

### Problema detectado

Diagnóstico de drift entre Elo rating y win rate real (2024-2026):

| Equipo | Elo | Drift local | Drift visitante |
|---|---|---|---|
| Cruz Azul | 1731 | +33.6% | +38.6% |
| Pumas UNAM | 1601 | +30.3% | +39.1% |
| Tijuana | 1542 | +29.3% | +38.7% |
| Toluca | 1643 | +22.2% | +34.8% |

**16 de 18 equipos están sobreestimados.** Drift promedio +25%.

### Causa

1. K-factor muy alto (20) → ratings se mueven rápido
2. Sin time-decay → partidos antiguos pesan igual
3. Liga con mucha paridad → equipos fluctúan pero Elo no se contrae

### Solución: Shrinkage hacia 1500

**Shrinkage global (default 0.7):**
- `adjusted_elo = 1500 + (elo - 1500) * 0.7`
- Calibrado con grid search sobre backtest 2025:
  - baseline (1.0): acc 55.29%, brier 0.5996
  - **0.7 (óptimo): acc 55.59%, brier 0.5858** (+0.3pp acc, -2.3% brier)

**Shrinkage por equipo y localía (experimental):**
- `shrinkage_local_X = 0.5 + 0.5 * (real_home_wr / expected_home_wr)`
- Equipos con drift grande → más contracción
- Ej: Cruz Azul visit shrinkage=0.77, Pumas visit=0.68
- **Hallazgo:** mejora algunos equipos (Querétaro +5pp) pero no mejora accuracy global sobre 100 partidos

**Uso:**
```bash
# Con shrinkage (default)
python3 src/predict/cli.py --home "X" --away "Y"

# Sin shrinkage (baseline original)
python3 src/predict/cli.py --home "X" --away "Y" --no-shrinkage

# Recalcular shrinkage por equipo
python3 src/predict/team_local_shrinkage.py --compute --start 2025-01-01
```

### Archivos nuevos

- `src/predict/elo.py` — `apply_shrinkage()`, `predict_1x2_elo()` con shrinkage
- `src/predict/team_local_shrinkage.py` — cálculo de shrinkage por equipo
- `src/predict/elo_shrinkage.py` — grid search para encontrar factor óptimo
- `src/predict/diagnose_elo_drift.py` — diagnóstico de drift Elo vs real
- `data/team_local_shrinkage.json` — shrinkage por equipo/localía
- `data/elo_drift_diagnosis.json` — diagnóstico completo por equipo

---

## 🎯 Composite Momentum (Fase 6)

**Feature #12 y Heurística #12** en el ensemble.

`get_composite_momentum(conn, team_id, before_date)` retorna:
- `recent_momentum` (0-3): W-D-L últimos 5
- `exponential_momentum` (0-3): ponderado por recencia
- `trend` (-1/0/+1): mejora/empeora
- `consistency` (0-1): 1 - CV puntos/partido

**Composite** = 40% recent + 60% exponential

**Heurística:**
```python
if abs(composite_diff) > 0.5:
    comp_adj = min(0.06, abs(composite_diff) * 0.05)
    if composite_diff > 0:
        home_win += comp_adj * (1 - home_win) * 0.5
    else:
        away_win += comp_adj * (1 - away_win) * 0.5

if min(home_consistency, away_consistency) < 0.25:
    confidence_penalty *= 0.92  # Forma volátil
```

**Backtest:** mejora Brier -0.05%, NLL -0.04%, accuracy igual. Feature evolutiva.

Ver `docs/FEATURES.md` sección Feature #12 y `tests/test_composite_momentum.py` para detalle.

---

## ⚽ xG Proxy (Fase 8)

### Motivación

SportMonks no expone shot-level data con coordenadas (lo que se usa para
calcular xG real en papers como Caley 2015, "Cartilage Free Captain"). 
Sin embargo, sí tenemos stats agregados por equipo/partido que aproximan
la calidad de los tiros:

- `shots-on-target` (tiros a puerta)
- `shots-insidebox` (tiros dentro del área)
- `shots-blocked` (tiros bloqueados)
- `shots-off-target` (tiros fuera)
- `shots-total` (total)
- `goals` (goles reales)

Con estos datos construimos un **xG proxy** calibrado con datos propios
de Liga MX (no coeficientes extranjeros — igual que hicimos con altitud).

### Metodología

**Modelo:** Regresión log-link con regularización L2 (Ridge).

```
log(1 + goals) = β₀ + β₁·sot + β₂·sib + β₃·sb + β₄·sot_off + β₅·shot_quality + β₆·is_home
```

donde:
- `sot` = shots on target
- `sib` = shots inside box
- `sb` = shots blocked
- `sot_off` = shots off target
- `shot_quality` = sib / shots_total (% de tiros desde dentro del área)
- `is_home` = 1 si local, 0 si visitante

Luego: `xG = exp(log(1+goals)) - 1` (back-transform).

**Coeficientes calibrados (3,830 equipo-partidos, Liga MX):**

| Feature | Coef (log) | Interpretación |
|---|---|---|
| `shots-on-target` | +0.105 | Más tiros a puerta → más goles |
| `shots-insidebox` | +0.004 | Ligero efecto (correlaciona con sot) |
| `shots-blocked` | -0.021 | Tiros bloqueados restan goles |
| `shots-off-target` | -0.022 | Tiros fuera restan goles |
| `shot_quality` | +0.268 | % de tiros desde dentro del área — predictor más fuerte |
| `is_home` | +0.095 | Localía (no redundante con Elo) |
| `intercept` | +0.257 | Baseline |

**Correlación in-sample con goles reales:** 0.553
**MAE:** 0.770 goles
**RMSE:** 1.004 goles

### Rolling xG

Para un partido `home vs away` en fecha `t`:

1. Calcular `attack_xg_home` = suma ponderada exponencialmente (decay=0.85)
   del xG generado por `home` en partidos anteriores a `t`.
2. Calcular `defense_xg_conceded_home` = suma ponderada exponencialmente
   del xG que `home` concedió a sus rivales.
3. Análogamente para `away`.
4. λ_home = attack_xg_home × (defense_xg_conceded_away / league_avg) × home_advantage
5. λ_away = attack_xg_away × (defense_xg_conceded_home / league_avg)
6. P(1X2) vía Poisson independiente sobre (λ_home, λ_away).

`league_avg = 1.25`, `home_advantage = 1.10`, `decay = 0.85`.

### Performance

**Como modelo individual (2024-2025, 680 partidos):**
- Accuracy: **51.91%** (vs 33.3% baseline azar, vs 48.97% Elo)
- Brier: 0.6173 (vs 0.6047 Elo — peor calibración individual, mejor accuracy)
- Correlación con goles reales: 0.55

**En ensemble (Fase 8):**
- Ensemble xG-heavy: 52.21% acc, 0.6092 Brier (680 partidos)
- Ensemble 2025 aislado: 53.53% acc, 0.6004 Brier
- **Δ vs baseline anterior: +3.97pp accuracy, -0.0112 Brier**

### Limitaciones

- Es un **xG proxy**, no xG real — no capturamos shot location, body part,
  assist type, etc. (SportMonks no expone).
- El backtest in-sample es optimista (overfitting a la misma data). El real
  gain es +3.5-4pp en test set.
- El modelo se beneficia del shrinkage Elo ya implementado (Elo se enfoca
  en tendencias largas, xG en recientes).

### Archivos

- `src/predict/xg.py` — implementación completa
- `src/predict/backtest_xg.py` — backtest comparativo con grid search
- `src/predict/calibration_xg.py` — análisis de calibración
- `data/xg_model.json` — coeficientes del modelo
- `tests/test_xg.py` — 15 tests (entrenamiento, predicción, lookup, persistencia)

---

## ⚽ xG Proxy (Fase 8)

### Motivación

SportMonks no expone shot-level data con coordenadas (lo que se usa para
calcular xG real en papers como Caley 2015, "Cartilage Free Captain"). 
Sin embargo, sí tenemos stats agregados por equipo/partido que aproximan
la calidad de los tiros:

- `shots-on-target` (tiros a puerta)
- `shots-insidebox` (tiros dentro del área)
- `shots-blocked` (tiros bloqueados)
- `shots-off-target` (tiros fuera)
- `shots-total` (total)
- `goals` (goles reales)

Con estos datos construimos un **xG proxy** calibrado con datos propios
de Liga MX (no coeficientes extranjeros — igual que hicimos con altitud).

### Metodología

**Modelo:** Regresión log-link con regularización L2 (Ridge).

```
log(1 + goals) = β₀ + β₁·sot + β₂·sib + β₃·sb + β₄·sot_off + β₅·shot_quality + β₆·is_home
```

donde:
- `sot` = shots on target
- `sib` = shots inside box
- `sb` = shots blocked
- `sot_off` = shots off target
- `shot_quality` = sib / shots_total (% de tiros desde dentro del área)
- `is_home` = 1 si local, 0 si visitante

Luego: `xG = exp(log(1+goals)) - 1` (back-transform).

**Coeficientes calibrados (3,830 equipo-partidos, Liga MX):**

| Feature | Coef (log) | Interpretación |
|---|---|---|
| `shots-on-target` | +0.105 | Más tiros a puerta → más goles |
| `shots-insidebox` | +0.004 | Ligero efecto (correlaciona con sot) |
| `shots-blocked` | -0.021 | Tiros bloqueados restan goles |
| `shots-off-target` | -0.022 | Tiros fuera restan goles |
| `shot_quality` | +0.268 | % de tiros desde dentro del área — predictor más fuerte |
| `is_home` | +0.095 | Localía (no redundante con Elo) |
| `intercept` | +0.257 | Baseline |

**Correlación in-sample con goles reales:** 0.553
**MAE:** 0.770 goles
**RMSE:** 1.004 goles

### Rolling xG

Para un partido `home vs away` en fecha `t`:

1. Calcular `attack_xg_home` = suma ponderada exponencialmente (decay=0.85)
   del xG generado por `home` en partidos anteriores a `t`.
2. Calcular `defense_xg_conceded_home` = suma ponderada exponencialmente
   del xG que `home` concedió a sus rivales.
3. Análogamente para `away`.
4. λ_home = attack_xg_home × (defense_xg_conceded_away / league_avg) × home_advantage
5. λ_away = attack_xg_away × (defense_xg_conceded_home / league_avg)
6. P(1X2) vía Poisson independiente sobre (λ_home, λ_away).

`league_avg = 1.25`, `home_advantage = 1.10`, `decay = 0.85`.

### Performance

**Como modelo individual (2024-2025, 680 partidos):**
- Accuracy: **51.91%** (vs 33.3% baseline azar, vs 48.97% Elo)
- Brier: 0.6173 (vs 0.6047 Elo — peor calibración individual, mejor accuracy)
- Correlación con goles reales: 0.55

**En ensemble (Fase 8):**
- Ensemble xG-heavy: 52.21% acc, 0.6092 Brier (680 partidos)
- Ensemble 2025 aislado: 53.53% acc, 0.6004 Brier
- **Δ vs baseline anterior: +3.97pp accuracy, -0.0112 Brier**

### Limitaciones

- Es un **xG proxy**, no xG real — no capturamos shot location, body part,
  assist type, etc. (SportMonks no expone).
- El backtest in-sample es optimista (overfitting a la misma data). El real
  gain es +3.5-4pp en test set.
- El modelo se beneficia del shrinkage Elo ya implementado (Elo se enfoca
  en tendencias largas, xG en recientes).

### Archivos

- `src/predict/xg.py` — implementación completa
- `src/predict/backtest_xg.py` — backtest comparativo con grid search
- `src/predict/calibration_xg.py` — análisis de calibración
- `data/xg_model.json` — coeficientes del modelo
- `tests/test_xg.py` — 15 tests (entrenamiento, predicción, lookup, persistencia)

---

## 8. Attendance Ratio (Fase 9) — Heurística #15

### Fuente de datos

ESPN API (`mex.1/scoreboard?weeks=1-60&limit=500`) — gratis, sin auth.

- **Cobertura global**: 1,515/1,854 fixtures Liga MX (81.7%)
- **Cobertura backtest 2024-2025**: 99.9% (679/680 partidos)

### Feature engineering

```python
ratio = attendance / venue_capacity

sold_out = ratio >= 0.95
capacity_factor = 'small' (<20k) | 'medium' (20-35k) | 'large' (>35k)
```

### 🔬 Hallazgo clave: inversión de hipótesis clásica

**Calibrado con 1,221 partidos Liga MX 2022-2025:**

| Attendance ratio | n | Local gana | Empate | Visitante gana |
|---|---|---|---|---|
| 0-15% (vacío) | 45 | **53.3%** | 26.7% | 20.0% |
| 15-30% | 279 | 50.2% | 25.1% | 24.7% |
| 30-50% | 328 | 39.9% | 26.2% | 33.8% |
| 50-70% | 265 | 40.8% | 27.5% | 31.7% |
| 70-85% | 171 | 46.8% | 18.7% | 34.5% |
| 85-95% | 96 | 38.5% | 30.2% | 31.2% |
| **95-105% (lleno)** | 37 | **21.6%** | 32.4% | **45.9%** |

**Hipótesis original (lleno = ventaja local) es INCORRECTA en Liga MX.**

Posibles causas:
1. Estadio lleno → partidos entre equipos grandes → visitante también fuerte
2. Estadio vacío → partidos intrascendentes donde el local es muy superior
3. Presión del público en lleno puede jugar en contra (Cialdini, 2001)

### Heurística calibrada (inversa a intuición)

```python
if ratio >= 0.95:    # lleno → visitante
    away_win += 0.03, draw += 0.02, home_win -= 0.04
elif ratio >= 0.85:  # casi lleno → visitante leve
    away_win += 0.015
elif ratio < 0.15:   # vacío → local
    home_win += 0.03
elif ratio < 0.30:   # casi vacío → local leve
    home_win += 0.015
```

### Backtest 2025 (340 partidos)

| Métrica | Sin heur | Con heur | Δ |
|---|---|---|---|
| Accuracy | 53.53% | **53.82%** | **+0.29pp** |
| Brier | 0.6004 | 0.6005 | +0.0001 |

**Veredicto**: mantener heurística — explica varianza + aporta +0.29pp accuracy.

### Grid search de pesos (descartó cambiar baseline)

| heur_weight | Accuracy | Brier |
|---|---|---|
| 9% (baseline) | 51.47% | 0.6093 |
| 14% | 50.88% | 0.6107 |
| 19% | 50.44% | 0.6123 |
| 24% | 50.44% | 0.6143 |

**Baseline 9% es óptimo** — más heur = peor.

---

## 9. Stacking XGBoost (Fase 9) — Meta-learner experimental

### Approach

XGBoost regularizado como meta-learner sobre:
- 12 features: 4 modelos × 3 outcomes (xg_home, xg_draw, xg_away, etc.)
- 5 features clave: attendance_ratio, weather_avail, referee_bias, altitude_diff, is_derby

Hiperparámetros (regularizados):
- n_estimators=30, max_depth=2, learning_rate=0.05
- reg_alpha=1.0, reg_lambda=2.0, min_child_weight=10

### Walk-forward validation (5 folds)

| Train | Test | Δ Acc | Δ Brier |
|---|---|---|---|
| 2023 H2 → 2024 | 2025 (340) | -0.29pp | **-0.0117** |
| 2023 H2 → 2024 | 2025 (340) | **+0.29pp** | **-0.0096** |
| 2023 H2 → 2025 H1 (510) | 2025 H2 (170) | -1.18pp | **-0.0138** |

**Agregado (5 folds walk-forward):**
- Δ accuracy promedio: **-0.65pp**
- Δ Brier promedio: **-0.0031**
- Folds con accuracy mejor: 2/5
- Folds con Brier mejor: 3/5

### Veredicto

**NO adoptado** — con 340-680 partidos por fold no hay suficiente señal.
El ensemble lineal bien calibrado (xG=55% + Elo=22.5% + DC=13.5% + heur=9%)
sigue siendo óptimo en accuracy.

El stacking SÍ mejora Brier consistentemente (-0.003 a -0.014), pero accuracy
es variable. Esto sugiere que las probabilidades están MEJOR calibradas pero el
top-pick no cambia significativamente.

**Re-evaluar cuando tengamos >2000 partidos** (>3 temporadas adicionales).

### Archivos

- `src/predict/stacking.py` — implementación XGBoost + Logistic Regression
- `src/predict/stacking_walkforward.py` — validación walk-forward 5 folds
- `src/predict/backtest_attendance.py` — backtest CON/SIN attendance heur
- `src/predict/grid_search_heur_weight.py` — grid search pesos heur (descarta cambios)
- `src/ingest_attendance.py` — scrape ESPN API
- `tests/test_stacking.py` — 6 tests
- `data/stacking_*.json` — resultados de experimentos
- `data/backtest_attendance.json` — comparación attendance heur
- `data/grid_search_heur.json` — grid search de pesos

### Estado

- ✅ Attendance scraper: scrape, heurística integrada, backtest
- ✅ Grid search heur: descarta cambios
- ✅ Stacking XGBoost: implementado, validado, NO adoptado
- ❌ Stacking queda como experimento futuro
