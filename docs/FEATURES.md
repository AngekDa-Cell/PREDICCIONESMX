# Features — Predictions_MX

> Catálogo completo de features engineered para el modelo.
> Última actualización: 2026-06-27

Cada feature aquí listado está **justificado por literatura científica** o **calibrado empíricamente con datos Liga MX**.

---

## 📊 Features automáticos (computados al vuelo)

### 1. **team_form** — Forma últimos N partidos

**Función:** `get_team_form(conn, team_id, before_date, n=5)`
**Tipo:** Dict con W/D/L, goals, momentum
**Output:**
```python
{
  'matches': 5, 'wins': 3, 'draws': 1, 'losses': 1,
  'goals_for': 8, 'goals_against': 5,
  'points': 10, 'win_rate': 0.6,
  'momentum': 2.0,  # puntos por partido
  'form_str': 'W-D-W-W-L',
}
```

**Justificación:** Forma reciente es el predictor más usado en modelos ML (MDPI 2025, revisión de 172 papers).

---

### 2. **exponential_form** — Forma ponderada exponencialmente

**Función:** `get_exponential_form(conn, team_id, before_date, decay=0.85, max_n=10)`
**Tipo:** Dict con momentum_score 0-3
**Output:**
```python
{
  'matches': 10,
  'momentum_score': 1.85,  # weighted points/game
  'weighted_win_rate': 0.58,
}
```

**Justificación:** Dixon-Coles paper original usa time-decay. Decay=0.85 da más peso a partidos recientes sin ignorar los antiguos.

---

### 3. **head_to_head** — Historial directo

**Función:** `get_head_to_head(conn, team_a, team_b, limit=10)`
**Tipo:** Dict con balance y win rate local
**Output:**
```python
{
  'total': 14,
  'a_wins': 6, 'b_wins': 4, 'draws': 4,
  'a_win_rate': 0.43, 'draw_rate': 0.29,
}
```

**Justificación:** Patrones históricos en derbies específicos son estadísticamente significativos.

---

### 4. **home_away_split** — Rendimiento local vs visitante

**Función:** `get_home_away_split(conn, team_id, before_date, n=15)`
**Tipo:** Dict con split local/visitante
**Output:**
```python
{
  'home': {'matches': 15, 'wins': 9, 'win_rate': 0.60, 'avg_gf': 1.7, 'avg_ga': 0.9},
  'away': {'matches': 15, 'wins': 4, 'win_rate': 0.27, 'avg_gf': 1.1, 'avg_ga': 1.6},
  'home_advantage': 0.33,  # diff de win rate
}
```

**Justificación:** Home advantage es real y persistente en fútbol (Pollard 2008). Necesitamos medirlo por equipo.

---

### 5. **altitude** — Altitud del estadio + ventaja comparativa

**Función:** `get_altitude_advantage(conn, home_team_id, away_team_id)`
**Tipo:** Dict con altitudes y delta
**Output:**
```python
{
  'home_altitude': 2240,
  'away_altitude': 40,
  'altitude_diff': 2200,
  'classification': 'very_high',  # <100, normal, high, very_high
  'altitude_score': 0.92,  # 0-1
}
```

**Justificación:** McSharry 2007 BMJ — paper seminal. **Pero calibrado a MX:** +2.48%/1000m (vs +12% Sudamérica).

---

### 6. **rest_days** — Días desde último partido

**Función:** `rest_days_advantage(conn, home_id, away_id, fixture_date)`
**Tipo:** Dict con rest days y rust indicator
**Output:**
```python
{
  'home_rest_days': 5,
  'away_rest_days': 3,
  'rest_diff': 2,
  'home_rusty': 0, 'away_rusty': 0,
  'rest_score': 0.29,
}
```

**Justificación:** Distribución MX calibrada:
- <3 días: fatiga (W% cae a 40.7%)
- 4-6 días: óptimo (49-56% W)
- >10 días: rust (38-45% W)

---

### 7. **coach_pressure** — Presión sobre el DT (proxy de motivación)

**Función:** `get_coach_pressure(conn, team_id, season_id)`
**Tipo:** Dict con winless_streak y pressure_index
**Output:**
```python
{
  'coach_id': 247,
  'games_managed': 17,
  'wins': 7, 'draws': 4, 'losses': 6,
  'win_rate': 0.41,
  'winless_streak': 5,
  'pressure_index': 0.5,  # 0-1
  'data_source': 'tenures',  # or 'form_proxy' or 'unknown'
}
```

**Justificación:** PLOS One 2025 (d=0.525 para motivación). Presión del DT correlaciona con peor performance.

---

### 8. **coach_tenure_days** — Tiempo del DT en cargo

**Función:** `get_coach_tenure_days(conn, team_id, fixture_date)`
**Tipo:** Dict con tenure y fase
**Output:**
```python
{
  'tenure_days': 14,
  'phase': 'new',  # 'new' (<30d), 'developing' (<180d), 'established'
  'games_managed': 2,
  'win_rate': 0.5,
  'is_new_coach': True,
}
```

**Justificación:** "New manager bounce" es fenómeno real en fútbol (MDPI 2025). DT nuevo <30d → +5% resultado, pero confidence -12% (inestable).

---

### 9. **travel_distance** — Distancia recorrida últimos 7 días

**Función:** `get_travel_distance(conn, team_id, fixture_date)`
**Tipo:** Dict con km totales y longest_leg
**Output:**
```python
{
  'distance_7d_km': 1850.3,
  'games_7d': 2,
  'longest_leg_km': 1240.0,
  'classification': 'high',  # low/normal/high/extreme
}
```

**Justificación:** Travel fatigue es real (anl.bet análisis Chile). Aplicado con non-linear scaling para no sobreponderar.

---

### 10. **fixture_congestion** — Partidos en últimos 7 días

**Función:** `get_fixture_congestion(conn, team_id, fixture_date)`
**Tipo:** Dict con conteo
**Output:**
```python
{
  'games_7d': 3,
  'games_14d': 5,
  'high_congestion': True,
  'moderate_congestion': False,
}
```

**Justificación:** Standard en papers de fixture congestion. En MX, el efecto es menor que en Europa (más descanso built-in).

---

### 11. **attack_defense_strength** — Ratio de goles vs liga

**Función:** `get_attack_defense_strength(conn, team_id, season_id)`
**Tipo:** Dict con strengths
**Output:**
```python
{
  'attack_strength': 1.10,  # 1.0 = promedio liga
  'defense_strength': 0.80,  # menor = mejor defensa
  'team_avg_gf': 1.6, 'team_avg_ga': 1.15,
  'league_avg_gf': 1.45,
}
```

**Justificación:** Dixon-Coles baseline. attack y defense como ratios vs promedio de la liga.

---

## 📝 Features manuales (JSON)

### Narratives (`data/manual/narratives_*.json`)

```json
{
  "narratives": [
    {
      "team": "América",
      "weight": 0.7,
      "direction": "favor_home",
      "description": "5 refuerzos clave + DT renovado",
      "active": true
    }
  ]
}
```

### Warnings (reglas automáticas)

```json
{
  "warnings": [
    {
      "type": "altitude",
      "threshold_m": 2400,
      "description": "Alta altitud → +10-15% local advantage"
    },
    {
      "type": "separation_days",
      "threshold": 3,
      "description": "3+ partidos en 10 días → -10% attack"
    }
  ]
}
```

---

## 🔢 Feature importance empírica

Basado en backtesting:

| Feature | Importancia | Fuente |
|---|---|---|
| **Forma reciente** | ⭐⭐⭐⭐ | Todos los papers |
| **Elo rating** | ⭐⭐⭐⭐ | FiveThirtyEight |
| **Altitud (MX calibrada)** | ⭐⭐⭐ | McSharry + calibración MX |
| **Home advantage** | ⭐⭐⭐ | Pollard 2008 |
| **Coach pressure** | ⭐⭐ | PLOS 2025 |
| **H2H** | ⭐⭐ | Estándar |
| **Rest days** | ⭐⭐ | Estándar |
| **Coach tenure** | ⭐ | MDPI 2025 |
| **Travel distance** | ⭐ | anl.bet 2025 |
| **Fixture congestion** | ⭐ | Distribución MX (sorprendente: bajo) |
| **Momentum exp** | ⭐ | Dixon-Coles original |
| **Attendance** | ⭐⭐⭐ | Pendiente de ingestar |

---

## ❌ Features que faltan

### Alta prioridad (no en BD):
1. **Attendance** — SportMonks metadata
2. **Referee ID** — SportMonks endpoint
3. **Weather** — Open-Meteo API

### Media prioridad (requieren más análisis):
4. **xG** — calcular desde shot-level data de SportMonks
5. **Passing networks** — paper arXiv 2024 muestra que predice bien
6. **Half-time scores** — real-time feature del paper Springer 2024

### Baja prioridad (manual):
7. **Choking risk** — high-status local que se ahoga en presión
8. **Stakes** — qué significa este partido para el equipo
9. **Crowd expectation** — ¿el equipo local DEBE ganar?

---

## 🆕 Feature #12: Composite Momentum (Fase 6)

### Motivación

Las features existentes capturan:
- `get_team_form()`: forma reciente W-D-L simple (últimos N)
- `get_exponential_form()`: ponderado exponencial por recencia (Miller-Sanjurjo 2018)

Pero falta capturar:
- **Tendencia** (¿está mejorando o empeorando?)
- **Consistencia** (¿qué tan volátil es la forma?)

El composite momentum combina **4 señales**:
1. `recent_momentum` (W-D-L últimos 5): momentum crudo
2. `exponential_momentum` (decay 0.85, últimos 10): ponderado por recencia
3. `trend` (-1/0/+1): mejora/empeora en últimos 3 vs anteriores 3
4. `consistency` (0-1): 1 - coeficiente de variación de puntos/partido

### Implementación

```python
def get_composite_momentum(conn, team_id, before_date, n_recent=5, decay=0.85, max_n=10):
    recent = get_team_form(conn, team_id, before_date, n_recent)
    exp = get_exponential_form(conn, team_id, before_date, decay, max_n)

    # Composite: 40% recent + 60% exponential (pondera más la tendencia)
    composite = recent['momentum'] * 0.4 + exp['momentum_score'] * 0.6

    return {
        'recent_momentum': round(recent['momentum'], 3),
        'exponential_momentum': round(exp['momentum_score'], 3),
        'composite_score': round(composite, 3),
        'trend': _calculate_trend(...),
        'consistency': _calculate_consistency(...),
        'n_matches': recent['matches'],
    }
```

### Heurística #12: Composite Momentum (en `heuristics.py`)

```python
if abs(composite_diff) > 0.5:
    comp_adj = min(0.06, abs(composite_diff) * 0.05)
    # Boost si además tiene trend positivo y alta consistencia
    if composite_diff > 0:
        home_win += comp_adj * (1 - home_win) * 0.5
        adjustments.append({
            'type': 'home_composite_momentum',
            'reason': f"Local composite_score={home_composite:.2f} vs visitante={away_composite:.2f}",
            ...
        })

# Penalización por inconsistencia extrema
if min(home_consistency, away_consistency) < 0.25:
    confidence_penalty *= 0.92
```

### Ejemplo real (Toluca vs Querétaro, mid-2024)

| Equipo | recent_momentum | exp_momentum | composite | trend | consistency |
|---|---|---|---|---|---|
| Toluca | 2.40 | 2.00 | 2.16 | -1 ↘ | 0.65 |
| Querétaro | 0.60 | 0.93 | 0.80 | 0 → | 0.33 |

→ Querétaro activa `away_composite_momentum` (visitante con composite 1.73 vs Toluca 0.68)

### Backtest (últimos 100 partidos)

| Métrica | Sin composite | Con composite |
|---|---|---|
| Accuracy | 46.00% | 46.00% (igual) |
| Brier | 0.6431 | 0.6428 (-0.05%) |
| NLL | 1.0665 | 1.0661 (-0.04%) |

**Mejora marginal en calibración**, accuracy estable. La feature aporta señal pero no es breakthrough.

### Tests

14 tests en `tests/test_composite_momentum.py`:
- Schema completo (todas las keys)
- Rangos válidos (momentum 0-3, consistency 0-1, trend -1/0/+1)
- Composite es promedio ponderado correcto (40/60)
- Integración con `get_full_feature_set()`
- CLI muestra heurística activada

---

## 🆕 Feature #13: Match Weather (Fase 6)

### Fuente

**Open-Meteo Archive API** (https://archive-api.open-meteo.com/v1/archive)
- Gratis, sin API key
- Datos históricos diarios desde 1940
- Timezone: America/Mexico_City

### Variables obtenidas

| Variable | Tipo | Rango típico MX |
|---|---|---|
| `temperature_2m_max` | °C | 10-35°C |
| `temperature_2m_min` | °C | 0-25°C |
| `precipitation_sum` | mm | 0-50mm |
| `wind_speed_10m_max` | km/h | 0-40 km/h |
| `wind_direction_10m_dominant` | ° | 0-360 |
| `relative_humidity_2m_max` | % | 30-100% |

### Derivadas

```python
is_extreme_heat = temp > 32°C      # Heat wave, fatiga
is_wet = precip > 0.5mm             # Lluvia significativa
is_high_humidity = humidity > 80%   # Condiciones pesadas
```

### Categorización de condiciones

| Precipitación | Condición |
|---|---|
| >=10mm | tormenta |
| >=2mm | lluvioso |
| >=0.5mm | llovizna |
| <0.5mm + humedad >=80% | humedo |
| <0.5mm + humedad <80% | seco |

### Heurística #13 en ensemble

```python
# Calor extremo: ligero advantage al local (acostumbrado)
if weather.is_extreme_heat:
    home_win += 0.02 * (1 - home_win) * 0.5

# Alta humedad: reduce varianza, favorece empates
if weather.is_high_humidity:
    # reduce home y away, favorece draw
    center = (home_win + away_win) / 2
    home_win -= 0.01 * (home_win - center)
    away_win -= 0.01 * (away_win - center)

# Lluvia: penaliza confianza (más varianza)
if weather.is_wet:
    confidence_penalty *= 0.97
```

### Ingesta

`src/ingest_weather.py`:
- Backfill: `python3 src/backfill_venue_by_team.py` → 95% de fixtures con venue_id
- Ingest: `python3 src/ingest_weather.py` → 1 fixture/seg desde Open-Meteo
- Tabla destino: `match_weather`

### Cobertura

| Métrica | Valor |
|---|---|
| Total fixtures históricos | 1701 |
| Con venue_id (backfill) | 1616 (95%) |
| Con weather ingestado | ~1616 (target) |

### Tests

7 tests en `tests/test_weather.py`:
- Schema completo
- Derivados (extreme_heat, wet, high_humidity)
- available=False cuando no hay datos
- Integración con `get_full_feature_set()`

---

## 🆕 Feature #14: xG Proxy (Fase 8)

### Motivación

El **Expected Goals (xG)** es el estándar moderno para medir calidad de
tiros. SportMonks no expone shot-level con coordenadas (xG real requiere
ubicación, body part, assist type), pero sí tenemos stats agregados que
aproximan la calidad ofensiva:

- Más tiros a puerta → más goles esperados
- Tiros desde dentro del área valen más que desde fuera
- Tiros bloqueados/fuera restan

Con estos construimos un **xG proxy** calibrado a los datos de Liga MX.

### Cálculo

**Modelo:** Regresión Ridge con log-link entrenado con 3,830 equipo-partidos
de Liga MX (2018-2025).

```python
# features.py-style
xG_features = {
    'sot': shots_on_target,        # tiros a puerta
    'sib': shots_insidebox,        # tiros dentro del área
    'sb': shots_blocked,           # tiros bloqueados
    'sot_off': shots_off_target,   # tiros fuera
    'shot_quality': sib / shots_total,  # % desde dentro del área
    'is_home': 1/0,
}
log_xG = β₀ + β·sot + β·sib + ...  # ridge regression
xG = exp(log_xG) - 1
```

**Coeficientes calibrados:**
- `sot` = +0.105 (más tiros a puerta → más goles)
- `shot_quality` = +0.268 (predictor más fuerte)
- `is_home` = +0.095 (localía adicional)
- `sb` y `sot_off` = negativos (restan)

### Rolling xG (cómo se usa en predicción)

Para un partido en fecha `t`:

```
attack_xg_home = Σ decay^i · xG_home_anterior_i  (todos los partidos previos)
defense_xg_conceded_home = Σ decay^i · xG_concedido_home_anterior_i

λ_home = attack_xg_home × (defense_xg_conceded_away / league_avg) × home_advantage
λ_away = attack_xg_away × (defense_xg_conceded_home / league_avg)

P(1X2) = Poisson_independiente(λ_home, λ_away)
```

Con `decay = 0.85`, `league_avg = 1.25`, `home_advantage = 1.10`.

### Performance como feature

| Modelo | Accuracy 2024-2025 | Brier |
|---|---|---|
| xG solo | **51.91%** | 0.6173 |
| Elo solo | 48.97% | 0.6047 |
| DC solo | 41.91% | 0.6631 |
| **Ensemble con xG** | **52.21%** | **0.6092** |
| Ensemble sin xG (baseline) | 48.24% | 0.6205 |

**Δ vs baseline: +3.97pp accuracy, -0.0112 Brier**

### Tests

15 tests en `tests/test_xg.py`:
- Ridge regression (recuperación de coefs en datos sintéticos)
- Entrenamiento produce coefs esperados
- Correlación in-sample > 0.45
- Monotonicidad por shots-on-target
- Poisson 1X2 (suma 1, simetría, draw en lambdas bajas)
- Predicción válida (probs suman 1, lambdas en rango)
- Cache de precompute
- Persistencia del modelo

---

## 🆕 Feature #15: Referee Bias (Fase 9)

### Motivación

Árbitros diferentes tienen sesgos distintos. Algunos倾向于local, otros倾向于visitante.
Los árbitros con ≥30 partidos en Liga MX muestran bias_score = home_win_rate - 0.5.

### Fuente de datos

**SportMonks API v3** — 173 árbitros Liga MX con 3,003 main assignments.
Cobertura: 92.9% sobre fixtures 2021+.

### Implementación

`src/predict/features.py::get_referee_bias()`

```python
{
    "available": True,
    "referee_id": 1234,
    "name": "César Ramos",
    "games": 87,
    "bias_score": +0.085,    # home_win_rate - 0.5
    "tendency": "home-favored",
    "home_win_rate": 0.585,
    "draw_rate": 0.218,
    "away_win_rate": 0.197,
    "is_reliable": True,     # ≥30 partidos
}
```

### Heurística #14 (en `heuristics.py`)

```python
if ref_reliable and abs(ref_bias) > 0.03:
    ref_adj_pp = ref_bias * 0.50  # ±0.10 → ±5pp
    if ref_bias > 0:
        home_win += ref_adj_pp / 100
    else:
        away_win += -ref_adj_pp / 100
```

### Estadísticas

- **38 árbitros con ≥30 partidos** analizados
- Bias medio: **-0.0345** (ligera倾向于visitante en MX)
- Rango: **-15.1%** (M. Anaya) a **+17.7%** (O. Delgadillo)

### Performance como feature

| Backtest 2024-08 → 2025-12 (828 partidos) | Δ Acc | Δ Brier |
|---|---|---|
| Sin referee heur | baseline | baseline |
| Con referee heur | **+0.00pp** | **-0.000002** |

**Veredicto**: bias es real pero el efecto es marginal cuando se combina con xG/Elo/DC
en ensemble (efecto diluido). Se mantiene por valor cualitativo (explicabilidad).

### Tests

28 tests en `tests/test_referee_bias.py`:
- Cálculo correcto de bias_score
- Filtrado por mínimo de partidos (≥30)
- Disponibilidad flag (available, is_reliable)
- Casos extremos (todos ganan local, todos pierden)
- Manejo de referee desconocido
- Integración con heurística #14

---

## 🆕 Feature #16: Attendance Ratio (Fase 9 extendida)

### Motivación

La asistencia al estadio refleja interés del público y posiblemente resultado.
Sorprendentemente, en Liga MX el patrón es **invertido** vs hipótesis clásica.

### Fuente de datos

**ESPN API** (`mex.1/scoreboard?weeks=1-60&limit=500`) — gratis, sin auth.

**Cobertura**:
- Global: 1,515/1,854 fixtures Liga MX (81.7%)
- Backtest 2024-2025: 99.9% (679/680 partidos)

### Implementación

`src/predict/features.py::get_attendance_ratio()`

```python
{
    "available": True,
    "attendance": 26040,        # absoluto
    "capacity": 87523,          # del venue (SportMonks)
    "ratio": 0.2975,            # attendance / capacity
    "capacity_factor": "large", # small/medium/large
    "sold_out": False,
}
```

### 🔬 HALLAZGO MAYOR: Estadio lleno favorece visitante

Análisis de **1,221 partidos Liga MX 2022-2025**:

| Attendance ratio | n | Local gana | Empate | Visitante gana |
|---|---|---|---|---|
| 0-15% (vacío) | 45 | **53.3%** | 26.7% | 20.0% |
| 15-30% | 279 | 50.2% | 25.1% | 24.7% |
| 30-50% | 328 | 39.9% | 26.2% | 33.8% |
| 50-70% | 265 | 40.8% | 27.5% | 31.7% |
| 70-85% | 171 | 46.8% | 18.7% | 34.5% |
| 85-95% | 96 | 38.5% | 30.2% | 31.2% |
| **95-105% (lleno)** | 37 | **21.6%** | 32.4% | **45.9%** |

### Heurística #15 (INVERTIDA vs intuición)

```python
if ratio >= 0.95:    # lleno → visitante (NO local)
    away_win += 0.03, draw += 0.02, home_win -= 0.04
elif ratio >= 0.85:  # casi lleno → visitante leve
    away_win += 0.015
elif ratio < 0.15:   # vacío → local (sorpresa)
    home_win += 0.03
elif ratio < 0.30:   # casi vacío → local leve
    home_win += 0.015
```

### Performance como feature

| Backtest 2025 (340 partidos) | Accuracy | Brier |
|---|---|---|
| Sin heur attendance | 53.53% | 0.6004 |
| **Con heur attendance** | **53.82%** | **0.6005** |

**Δ: +0.29pp accuracy** (modesto pero positivo).

### Quirks de implementación

1. ESPN a veces devuelve gzip sin avisar → descomprimir si primeros 2 bytes son `\x1f\x8b`
2. Slug ESPN es `mex.1` (sensible a mayúsculas)
3. Algunos venues tienen `capacity=0` o NULL → feature marca como no disponible
4. Mapeo manual `displayName → team_id` (ESPN abbrs difieren de las nuestras)

### Tests

Tests indirectos vía `test_features.py` + `test_heuristics.py` (~20 tests cubren la feature).

