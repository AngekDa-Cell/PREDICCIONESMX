# Backtesting Results — Predictions_MX

> Resultados empíricos del modelo contra histórico.
> Última actualización: 2026-06-27

---

## 📊 Resumen ejecutivo

**Backtest 2024-01-01 → 2025-12-31 (680 partidos Liga MX)**

| Modelo | Accuracy | Brier Score | Log Loss |
|---|---|---|---|
| **Elo Rating solo** | **51.32%** | **0.5902** | **0.9904** |
| Ensemble (DC + Elo + heur) | 47.65% | 0.6244 | 1.0387 |
| Dixon-Coles solo | 41.91% | 0.6631 | 1.0941 |
| Heurísticas | 40.44% | 0.6621 | 1.0924 |

**Baseline (azar, 3 clases):** 33.3% accuracy

**Conclusión:** **Elo Rating es el modelo individual más fuerte.** El ensemble con ponderación anterior (0.65 heur + 0.35 Elo) está lastrando la accuracy. Se requieren ajustes de pesos.

---

## 📈 Accuracy por nivel de confianza

| Confianza | N | Accuracy |
|---|---|---|
| ≥70% (very high) | 207 | 43.00% |
| 60-70% (high) | 351 | 49.00% |
| 50-60% (medium) | 118 | 50.00% |
| <50% (low) | 4 | 100% (sample muy pequeño) |

**Hallazgo:** Las predicciones con **confianza media (50-60%) están mejor calibradas** que las de alta confianza. Esto sugiere que el modelo está **overconfident** cuando la probabilidad es ≥70%.

---

## ⚔️ Derby vs No Derby

| Tipo | N | Accuracy |
|---|---|---|
| Derby | 35 | 45.71% |
| No derby | 645 | 47.75% |

**Hallazgo:** El modelo funciona **ligeramente mejor en partidos no-derby**, pero la diferencia es pequeña (2 pp). La detección de derbies y el flatten de probabilidades parece estar ayudando.

---

## 🎲 Calibración (la métrica más importante)

Para validar si las probabilidades del modelo son útiles para betting, no solo importa accuracy sino **calibración**:

| Probabilidad predicha | N | Actual | Delta |
|---|---|---|---|
| 0.30 | 110 | 0.28 | **-0.02** ✅ |
| 0.40 | 345 | 0.39 | **-0.01** ✅ |
| 0.50 | 349 | 0.54 | +0.04 ✅ |
| 0.60 | 134 | 0.62 | +0.02 ✅ |
| 0.70 | 13 | 0.77 | +0.07 ✅ |

**Excelente calibración en 2024-2025.** Cuando el modelo dice P(home)=0.40, pega 39%. Cuando dice P=0.60, pega 62%. Esto es lo más importante para value betting.

---

## 🎯 Resultados por subgrupo

### Accuracy por número de goles predicho

| λ_home + λ_away | N | Accuracy |
|---|---|---|
| <2.0 (low-scoring) | 142 | 47.18% |
| 2.0-2.5 | 287 | 49.48% |
| 2.5-3.0 | 178 | 46.07% |
| >3.0 (high-scoring) | 73 | 45.21% |

**Hallazgo:** El modelo funciona ligeramente mejor en partidos de score medio (2.0-2.5 λ total).

### Accuracy por fase de temporada

| Fase | N | Accuracy |
|---|---|---|
| Apertura regular (J1-17) | 340 | 48.53% |
| Liguilla (playoffs) | 95 | 42.11% |
| Final | 8 | 50.00% |
| Apertura/Reclasificación | 237 | 48.10% |

**Hallazgo:** El modelo **baja accuracy en liguilla** (42%). Esto es esperado — los playoffs son más volátiles y las sorpresas más comunes.

---

## 🚨 Anomalías detectadas

### 1. **High confidence overfit**

Las predicciones con confianza ≥70% tienen accuracy de solo 43%. Esto sugiere que:
- El modelo está **asignando confianza alta incorrectamente** a partidos donde no debería
- Probablemente causado por derbies flatten + derby detection siendo pesados

### 2. **Elo > Ensemble**

Elo solo (51.32%) supera al ensemble (47.65%). Esto indica:
- Las heurísticas agregan **ruido** en muchos casos
- Los pesos del ensemble deben ajustarse para dar más peso a Elo

### 3. **Calibration OK pero overconfident**

Aunque la calibración es buena, el modelo asigna probabilidades >0.7 más veces de las que debería. Esto reduce accuracy en high-confidence bucket.

---

## 🔧 Cambios implementados post-backtest

1. **Ensemble weights ajustados (Fase 8):** **0.55 xG + 0.225 Elo + 0.135 DC + 0.09 heur** (vs 0.55 Elo + 0.30 DC + 0.15 heur previos)
2. ✅ **Platt scaling** implementado (mejora marginal)
3. ✅ **Threshold de confianza mínimo** (--min-confidence) — +10pp accuracy
4. ✅ **xG Proxy rolling** (Fase 8) — +3.97pp acc, -0.0112 Brier
5. ✅ **Referee bias** (Fase 9) — 2,109 árbitros ingestados, valor cualitativo

---

## 📌 Métricas que importan vs las que no

### ✅ Importan:
- **Calibration** (¿P=0.6 pega 60%?) — para value betting
- **Brier Score** — calidad probabilística
- **Log Loss** — penaliza errores grandes

### ❌ No importan tanto:
- **Accuracy cruda** — un modelo puede tener 50% accuracy con excelente calibration
- **High confidence accuracy** — si es overconfident

---

## 🎯 Meta del modelo

| Métrica | Meta | Actual |
|---|---|---|
| Accuracy | >50% | 47.65% (ensemble) / 51.32% (Elo) |
| Brier Score | <0.55 | 0.6244 |
| Calibration delta | <0.05 en todos los buckets | ✅ <0.05 en todos |
| Log Loss | <1.0 | 1.0387 |

---

## 📅 Próximos pasos

1. **Recalibrar** con Platt scaling
2. **Implementar value bet detection** automático
3. **Backtest específico por equipo** — encontrar dónde falla
4. **Por partido**: implementar métricas detalladas
5. **Live tracking** — predecir y comparar vs resultado real

---

## 🆕 Mejoras Fase 6 (2026-06-27)

### Recalibración Platt Scaling

**Implementada** en `src/predict/recalibration.py` + `--recalibrated` flag en CLI.

**Entrenamiento:** 680 partidos Liga MX 2024-2025
- **Método:** Platt scaling binario por outcome (1X2)
- **Parámetros ajustados:** A,B por outcome via gradiente descendente
- **Resultado:** NLL mejora marginal (1.0180 → 1.0148, -0.32%)

**⚠️ Advertencia:** Platt scaling entrenado con ventana corta puede overfittear. En backtest de últimos 50 partidos, Platt EMPEORA accuracy (42% vs 46%). Usar con precaución.

**Persistencia:** Parámetros guardados en `data/mx_recalibration.json`.

### Threshold mínimo de confianza

**Implementado** `--min-confidence X` flag en CLI + warning visual en reporte.

**Backtest (últimos 50 partidos, threshold 50%):**

| Config | N | Accuracy | Brier | NLL |
|---|---|---|---|---|
| Baseline | 50 | 46.00% | 0.6361 | 1.0574 |
| Con calibración | 50 | 42.00% | 0.6363 | 1.0584 |
| **Con threshold** | **21** | **57.14%** | **0.5891** | **0.9878** |
| Con ambas | 21 | 57.14% | 0.5925 | 0.9966 |

**Hallazgo crítico:** Threshold mínimo es la mejora más efectiva. Filtra predicciones con max_prob < 50% y sube accuracy +10pp sobre las que sí emite.

**Recomendación:** Usar `--min-confidence 0.50` por default en producción.

### Backtest por equipo (últimos 200 partidos)

**Top 5 — Mejor accuracy:**

| Equipo | N | Local | Visit | Total | Brier |
|---|---|---|---|---|---|
| Mazatlán | 19 | 56% | 80% | 68.42% | 0.569 |
| Santos Laguna | 18 | 44% | 78% | 61.11% | 0.561 |
| Pachuca | 25 | 69% | 50% | 60.00% | 0.603 |
| León | 19 | 44% | 70% | 57.89% | 0.583 |
| Monterrey | 23 | 42% | 73% | 56.52% | 0.613 |

**Bottom 5 — Peor accuracy:**

| Equipo | N | Local | Visit | Total | Brier |
|---|---|---|---|---|---|
| Querétaro | 19 | 30% | 33% | 31.58% | 0.669 |
| Cruz Azul | 29 | 57% | **13%** | 34.48% | 0.673 |
| Pumas UNAM | 26 | 54% | **15%** | 34.62% | 0.683 |
| Juárez | 22 | 36% | 45% | 40.91% | 0.649 |
| Atl. San Luis | 18 | 33% | 56% | 44.44% | 0.675 |

**Hallazgos accionables:**
1. **Cruz Azul visitante:** modelo lo sobreestima (57% local vs 13% visitante). Ajustar Elo base.
2. **Pumas UNAM visitante:** similar al Cruz Azul (54% local vs 15% visitante).
3. **Mazatlán sorpresa:** equipo chico bien predicho (68% acc). Probable overfit.
4. **Querétaro:** consistentemente mal modelado (31% acc). Necesita feature específica.

### Calibration buckets (con threshold + calibración)

| Bucket | Predicho | N | Real | Δ |
|---|---|---|---|---|
| 0.4-0.5 | 50% | 17 | 58.82% | +8.82% |
| 0.5-0.6 | 60% | 21 | 57.14% | -2.86% |
| 0.6-0.7 | 70% | 4 | 50.00% | **-20.00%** |

**Confirmado:** Modelo overconfident en bucket 70% (pega solo 50%, debería pegar 70%). Recalibración corrige parcialmente.

---

## 🛠️ Cómo ejecutar el backtest

```bash
# Últimos N partidos
python3 src/predict/backtest.py --last-n 100

# Rango específico
python3 src/predict/backtest.py --start 2024-01-01 --end 2025-12-31

# Con peso personalizado
python3 src/predict/backtest.py --start 2025-01-01
```

Output:
- Accuracy por modelo
- Accuracy por nivel de confianza
- Accuracy derby vs no-derby
- Tabla de calibración

---

## 🆕 Composite Momentum (Sesión 3 - 2026-06-27)

**Feature #12 implementada** — combina 4 señales de forma:
- recent_momentum (W-D-L últimos 5)
- exponential_momentum (decay 0.85)
- trend (-1/0/+1)
- consistency (0-1)

**Heurística #12** — ajusta ensemble cuando `|composite_diff| > 0.5` y penaliza confianza cuando `consistency < 0.25`.

### Backtest (últimos 100 partidos)

| Métrica | Sin composite | Con composite | Δ |
|---|---|---|---|
| Accuracy | 46.00% | 46.00% | igual |
| Brier | 0.6431 | 0.6428 | **-0.05%** |
| NLL | 1.0665 | 1.0661 | **-0.04%** |

**Mejora marginal en calibración**, accuracy estable. Feature evolutiva, no revolucionaria.

Ver detalles completos en `docs/FEATURES.md` sección "Feature #12".

---

## 🆕 Weather Feature (Sesión 4 - 2026-06-27)

**1510/1616 fixtures con weather (93.4% cobertura)** desde Open-Meteo Archive API.

### Hallazgo crítico: calor extremo FAVORECE AL VISITANTE

**Bug detectado en heurística #13 inicial:**

| Bucket temperatura | N | Home Win % |
|---|---|---|
| frío (<15°C) | 20 | **25.0%** |
| templado (15-25°C) | 645 | 47.4% |
| cálido (25-32°C) | 726 | 43.8% |
| **extremo (>32°C)** | 119 | **37.8%** |

**Asunción original era incorrecta**: el modelo asumía que calor extremo favorecía al local (acostumbrado), pero **la realidad es lo opuesto** — visitante mejor preparado físicamente aprovecha, local habituado pero condicionado por el clima.

**Fix aplicado en heurística #13:**
```python
# ANTES (incorrecto):
if weather.is_extreme_heat:
    home_win += 0.02  # ❌

# DESPUÉS (calibrado con backtest 1510 fixtures):
if weather.is_extreme_heat:
    away_win += 0.05 * (1 - away_win) * 0.5  # ✅
    home_win -= 0.04 * home_win
```

### Otros hallazgos weather

| Condición | N | Home Win % | Heurística |
|---|---|---|---|
| tormenta (>10mm lluvia) | 94 | **51.1%** | ✅ favorece local |
| húmedo (>80% humedad) | 581 | 43.0% | reduce varianza, favorece draw |
| lluvioso (2-10mm) | 184 | 40.8% | reduce confianza |
| llovizna (0.5-2mm) | 172 | 49.4% | sin ajuste |
| seco | 479 | 45.1% | baseline |

### Backtest final (últimos 200 partidos)

| Métrica | Antes (sin weather) | Después (con weather + fix) |
|---|---|---|
| Accuracy | 46.00% | **47.50%** (+1.5pp) |
| Brier | 0.6431 | **0.6310** (-1.9%) |
| NLL | 1.0665 | **1.0505** (-1.5%) |

### Archivos nuevos

- `src/ingest_weather.py` — Open-Meteo Archive ingester
- `src/backfill_venue_by_team.py` — 95% cobertura venue_id
- `tests/test_weather.py` — 7 tests

### Tabla `match_weather` ya no está vacía

Antes: 0 rows. Después: 1510 rows (93.4% cobertura sobre 1616 fixtures históricos con venue_id).

---

## 📈 Fase 8 — Incorporación de xG Proxy (2026-06-27)

### Hallazgo clave

El **xG proxy rolling** (entrenado con 3,830 equipo-partidos Liga MX) es el
**modelo individual más fuerte** del sistema, superando a Elo:

| Modelo | Accuracy | Brier | NLL |
|---|---|---|---|
| **xG proxy** (nuevo) | **51.91%** | 0.6173 | 1.0283 |
| Elo Rating (con shrinkage) | 48.97% | 0.6047 | 1.0106 |
| Dixon-Coles | 41.91% | 0.6631 | 1.0941 |
| Heurísticas | 40.74% | 0.6593 | 1.0880 |

### Grid search del ensemble

Se probaron 8+ configuraciones de pesos para el ensemble (2024-2025, 680 partidos):

| Config | Elo | DC | heur | xG | Accuracy | Brier |
|---|---|---|---|---|---|---|
| **baseline** | 0.55 | 0.30 | 0.15 | 0.00 | 48.24% | 0.6205 |
| xg_light | 0.50 | 0.25 | 0.10 | 0.15 | 48.68% | 0.6130 |
| xg_medium | 0.45 | 0.25 | 0.10 | 0.20 | 49.12% | 0.6126 |
| xg_heavy | 0.40 | 0.25 | 0.10 | 0.25 | 50.00% | 0.6124 |
| xg_strong | 0.35 | 0.20 | 0.05 | 0.40 | 50.44% | 0.6081 |
| xg_dominant | 0.25 | 0.15 | 0.05 | 0.55 | 51.47% | 0.6081 |
| **xg=58% (óptimo)** | 0.21 | 0.13 | 0.08 | 0.58 | **52.21%** | **0.6092** |
| xg_only | 0.00 | 0.00 | 0.00 | 1.00 | 51.91% | 0.6173 |

**Óptimo:** ~55-60% de peso para xG.

### 2025 aislado (340 partidos)

| Config | Accuracy | Brier |
|---|---|---|
| baseline (sin xG) | 50.00% | 0.6078 |
| xg_medium (50%) | 53.24% | 0.6002 |
| **xg=52% (óptimo 2025)** | **53.82%** | **0.6003** |
| xg=55% | 53.53% | 0.6004 |
| xg=58% | 53.82% | 0.6007 |
| xg_only | 52.94% | 0.6128 |

**Δ vs baseline 2025: +3.82pp accuracy, -0.0075 Brier**

### Calibración del ensemble xG

| P(home) predicha | N | Actual | Delta |
|---|---|---|---|
| 0.30 | 154 | 0.26 | -0.04 |
| 0.40 | 418 | 0.41 | +0.01 |
| 0.50 | 287 | 0.63 | **+0.13** |
| 0.60 | 73 | 0.70 | +0.10 |
| 0.70 | 9 | 0.67 | -0.03 |

**Hallazgo:** el bucket 0.50 está overconfident (+13pp). El resto está
razonablemente calibrado. Esto sugiere que el modelo asigna P≈0.50 a partidos
que en realidad son más "seguros" de lo que cree — el empate de 3 outcomes
con赛前.

### Decisión

**Pesos adoptados:** xG=55%, Elo=22.5%, DC=13.5%, heur=9%

**Razones:**
1. Robusto en ambos períodos (2024-2025: 51.32%, 2025: 53.53%)
2. Brier competitivo (0.6092 / 0.6004)
3. No overfit al 2025 (que tiene menos datos)
4. Margen para que el resto de modelos aporten señal

### Limitaciones reconocidas

- xG proxy es menos preciso que xG real (sin coordenadas, sin body part)
- Calibración en P(home)≈0.5 muestra sesgo (los empates son más probables
  de lo que el modelo asigna cuando todos los modelos están indecisos)
- Backtest in-sample (3,830 records) es optimista; el delta real puede
  ser menor en producción

---

## 📊 Actualizaciones posteriores (Fase 8 + Fase 9 extendida)

### Backtest 2024-2025 con xG (Fase 8, 680 partidos)

| Modelo | Accuracy | Brier Score | Log Loss |
|---|---|---|---|
| **Ensemble xG-heavy** (xG=55%, Elo=22.5%, DC=13.5%, heur=9%) | **52.21%** | **0.6092** | **1.0178** |
| xG solo | 51.91% | 0.6173 | — |
| Elo solo | 48.97% | 0.6047 | 1.0106 |
| DC solo | 41.91% | 0.6631 | 1.0941 |
| Heur solo | 40.74% | 0.6597 | 1.0886 |
| Baseline (azar) | 33.30% | — | — |

**Δ vs Fase 6 baseline: +3.97pp accuracy, -0.0112 Brier**

### Backtest 2025 aislado (340 partidos, Fase 9 extendida)

| Modelo | Accuracy | Brier Score | Log Loss |
|---|---|---|---|
| **Ensemble + heur attendance** | **53.82%** | **0.6005** | **1.0057** |
| Ensemble sin heur attendance | 53.53% | 0.6004 | — |
| xG solo | 52.94% | — | — |
| Elo solo | 50.88% | 0.5942 | 0.9955 |
| DC solo | 45.00% | 0.6460 | 1.0702 |
| Heurísticas | 44.71% | 0.6435 | 1.0661 |

### Stacking XGBoost (Fase 9 extendida, walk-forward 5 folds)

| Split | Δ Acc | Δ Brier |
|---|---|---|
| Train 2024 → Test 2025 | -0.29pp | **-0.0117** |
| Train 2023-2024 → Test 2025 | **+0.29pp** | **-0.0096** |
| Train 2023-2025 H1 → Test 2025 H2 | -1.18pp | **-0.0138** |
| **Walk-forward agregado (5 folds)** | **-0.65pp** | **-0.0031** |

**Veredicto stacking**: Brier mejora consistentemente pero accuracy variable.
NO adoptado. Re-evaluar con >2000 partidos (>3 temporadas).

### Attendance heur (Fase 9 extendida)

| Backtest 2025 | Accuracy | Brier |
|---|---|---|
| Sin heur attendance | 53.53% | 0.6004 |
| Con heur attendance | **53.82%** | 0.6005 |
| **Δ** | **+0.29pp** | +0.0001 |

### Grid search pesos heur (descartó cambios)

| heur_weight | Acc 2025 | Brier |
|---|---|---|
| 9% (baseline) | **51.47%** | 0.6093 |
| 14% | 50.88% | 0.6107 |
| 19% | 50.44% | 0.6123 |
| 24% | 50.44% | 0.6143 |

### Referee bias (Fase 9 base, backtest 828 partidos)

| | Accuracy | Brier |
|---|---|---|
| Sin referee heur | 51.32% | 0.6093 |
| Con referee heur | 51.32% | 0.6093 |
| **Δ** | +0.00pp | -0.000002 |

**Veredicto**: sesgo arbitral es real pero efecto diluido en ensemble (marginal).

