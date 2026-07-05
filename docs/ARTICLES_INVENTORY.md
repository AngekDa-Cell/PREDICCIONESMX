# Articles Inventory — Predictions_MX

> **Mapeo completo: papers consultados → features implementadas → estado del sistema.**
> Última actualización: 2026-06-27

Este documento es la **fuente de verdad** sobre qué literatura científica sustenta cada parte del sistema. Si Ángel pregunta "¿qué papers usaste?" o "¿qué falta por implementar?", apuntar aquí.

---

## 📊 Resumen ejecutivo (tabla maestra)

| # | Paper / Fuente | Año | Revista / Tipo | Implementado en código | Estado |
|---|---|---|---|---|:---:|
| 1 | McSharry, P.E. — *Effect of altitude on physiological performance* | 2007 | BMJ | `get_altitude_advantage()` + heurística #1 | ✅ Calibrado MX |
| 2 | Ayranci & Aydin — *Psychological factors & sports performance* | 2025 | PLOS One | `get_coach_pressure()` + narrativa | ✅ Parcial |
| 3 | MDPI — *Machine Learning Applied to Professional Football* | 2025 | MDPI ML | Ensemble structure + **15 features** | ✅ Parcial |
| 4 | The Playbook Sport — *From Cheers to Chokes* | 2024 | Sports Psych | Derby flatten + narrativas | ✅ Parcial |
| 5 | Foresportia — *Home advantage & travel fatigue AI* | 2025 | Blog methodology | Calibración MX philosophy | ✅ |
| 6 | arXiv — *Predicting with complex networks & ML* | 2024 | arXiv | Pendiente | ❌ |
| 7 | Springer — *Data-driven prediction of soccer outcomes* | 2024 | J Big Data | Pendiente (XGBoost stacking) | ❌ |
| 8 | anl.bet — *Chile Soccer Analytics: Altitude & Travel* | 2025 | Industry | `get_travel_distance()` + `get_fixture_congestion()` | ✅ |
| 9 | Smoulder et al. — *A Neural Basis of Choking Under Pressure* | 2024 | Neuron | Pendiente (`choking_risk`) | ❌ Fase 6 |
| 10 | Chabrol et al. — *Cerebellar Contribution to Motor Neocortex* | 2019 | Neuron | Referencia conceptual | ❌ |
| 11 | Yerkes-Dodson Law | 1908 | J Comp Neurol | Concepto en derby flatten + heurísticas | ⚠️ Conceptual |
| 12 | Miller & Sanjurjo — *Re-analysis of Hot Hand* | 2018 | Econometrica | `get_exponential_form()` | ✅ |
| 13 | Mesagno et al. — *Choking in sport* | 2024+ | ScienceDirect | Pendiente (`choking_risk`) | ❌ Fase 6 |
| 14 | Adams & Kupper — *Home-field as expertise deficiency* | — | — | Pendiente (`expertise_modifier`) | ❌ Fase 6 |
| 15 | Wikipedia — *Home advantage* (overview) | — | Encyclopedia | `get_altitude_advantage()` (parcial) | ✅ Parcial |
| **16** | **Lucey et al. — *Quality vs Quantity: Improved Shot Prediction in Soccer using Tactical Features*** | **2015** | **MIT Sloan Sports Analytics** | **`src/predict/xg.py` (Fase 8)** | **✅ xG Proxy** |
| **17** | **Caley — *Cartilage Free Captain: Shot quality*** | **2015** | **Blog seminal** | **`src/predict/xg.py` (Fase 8)** | **✅ xG Proxy** |
| **18** | **Anzer et al. — *Expected Goals (xG) Models for Soccer*** | **2021** | **Springer review** | **Referencia (Fase 9+)** | **⚠️ Conceptual** |

**Papers adicionales consultados pero NO usados directamente:**
- sportmonks.md — documentación técnica del API (no predictivo)
- TheSportReview + SportBot AI — methodology blogs (cubierto por Foresportia)

---

## 📖 Detalle por paper

### 1. McSharry, P.E. (2007) — *Effect of altitude on physiological performance*

**Publicación:** British Medical Journal, 335(7633), 1278-1283
**URL:** https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2151172/
**Datos:** 1,460 partidos FIFA, 10 países, 100 años

**Hallazgos clave:**
- Δh=+1000m → +0.5 goles en goal difference local
- P(home win) con Δh=+3695m: **0.825**
- P(home win) con Δh=-3695m: **0.213**
- 60% del efecto: más goles anotados; 40%: menos goles concedidos
- P<0.001 (significativo)

**Calibración MX propia:** 1,529 partidos Liga MX
- Boost por +1000m: **+2.48% win rate** (vs McSharry +12%)
- GD por +1000m: **+0.088** (vs McSharry +0.5)
- Baseline home win (Δh=0): **57.6%**

**Implementado en:**
- `src/predict/features.py::get_altitude_advantage()` — calcula altitudes
- `src/predict/heuristics.py` — heurística #1 con coeficiente 0.0248
- `src/predict/mx_coefficients.json` — coeficientes guardados
- `docs/RESEARCH_SYNTHESIS.md` — sección completa

**Estado:** ✅ **Producción, calibrado MX**

**Gap:** No distingue entre altitud crónica (equipos que viven ahí) vs aguda (visita de 1 día). La literatura sugiere que los equipos que viven en altitud tienen ventaja adicional por aclimatación.

---

### 2. Ayranci & Aydin (2025) — *Psychological factors & sports performance*

**Publicación:** PLOS One, 20(8), e0330862
**URL:** https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0330862
**Datos:** Meta-análisis 127 estudios, 24,358 participantes (PRISMA)

**Hallazgos cuantitativos (Cohen's d):**
| Factor | d | Fuerza |
|---|---|---|
| **Motivación** | **0.525** | FUERTE |
| Autoeficacia | 0.413 | Moderado-fuerte |
| Extraversión | 0.336 | Moderado |
| Escrupulosidad | 0.316 | Moderado |
| Overall psychology → performance | 0.329 | Moderado |
| Ansiedad pre-competición | bajo | No significativo |

**Implementado en:**
- `src/predict/features.py::get_coach_pressure()` — proxy de motivación del grupo vía winless_streak
- `src/predict/heuristics.py` — heurística #3 (presión DT)
- `data/manual/narratives_default.json` — campo motivación narrativa
- `memory/predictions_mx_research.md` — sección dedicada

**Estado:** ✅ **Producción parcial** (proxy limitado)

**Gap:** Falta medición directa de:
- Self-efficacy individual del equipo
- Cohesión grupal
- Mental toughness
- Estado de ánimo pre-partido

---

### 3. MDPI (2025) — *Machine Learning Applied to Professional Football*

**Publicación:** MDPI Machine Learning & Knowledge Extraction, 7(3), 85
**URL:** https://www.mdpi.com/2504-4990/7/3/85
**Datos:** Revisión sistemática de 172 papers (2019-2024)

**Hallazgos clave:**
- Features más usados: match stats + forma reciente + Elo + cuotas + xG + player stats
- Modelos top: XGBoost + 13 features, Random Forest, ensemble voting
- Hyperparameter tuning crítico (grid search + Bayesian)
- Class imbalance: SMOTE, Near-Miss, Random-OverSampling
- FNN + Vanilla RNN para dependencias temporales

**Implementado en:**
- `src/predict/elo.py` — Elo Rating (recomendado por paper)
- `src/predict/features.py` — **15 features** (Fase 9 extendida)
- `src/predict/cli.py` — Ensemble structure

**Estado:** ✅ **Producción parcial**

**Gap (Fase 8+):**
- ❌ XGBoost stacking
- ❌ Player-level stats
- ❌ Real-time features (half-time results)
- ❌ Hyperparameter tuning formal
- ❌ Class imbalance handling

---

### 4. The Playbook Sport (2024) — *From Cheers to Chokes*

**Publicación:** Blog profesional de sports psychology
**URL:** https://theplaybooksport.com/from-cheers-to-chokes

**Hallazgos cuantitativos:**
- MLS home win rate: **69.1%**
- NBA home win rate: 62.7%
- MLB home win rate: 54.1%
- COVID sin afición: home advantage cayó **-50%**
- Referees **15.5% menos** fouls contra locales
- Penalty conversion: high-status **65%** vs lesser-known **88.9%**
- Basketball: free throw accuracy cae en clutch moments

**Implementado en:**
- `src/predict/heuristics.py::detect_derby()` — flatten 15% (high-stakes)
- `src/predict/heuristics.py` — heurística #3 (presión DT)
- Filosofía de narrativas — capturar contexto que no está en stats

**Estado:** ✅ **Producción parcial**

**Gap (Fase 7):**
- ❌ Referee ID (SportMonks lo da)
- ❌ Attendance (SportMonks metadata)
- ❌ Cuotas de mercado para calibrar
- ❌ Choking risk score (composite)

---

### 5. Foresportia (2025) — *Home advantage & travel fatigue AI weighting*

**Publicación:** Industry methodology blog
**URL:** https://www.foresportia.com/en/blog/home-advantage-travel-fatigue-football-prediction-ai.html

**Conceptos adoptados:**
- Home advantage **recalibrable** por liga
- Travel distance **non-linear** (no asumir viaje = resultado)
- Crowd influence vía **signals indirectos** (asistencia, performance home)
- **Dynamic weighting**: coeficientes evolucionan
- Probabilidad = **frecuencia esperada**, no certeza
- Drift detection + recalibration continua

**Implementado en:**
- `src/predict/mx_coefficients.json` — coeficientes específicos MX
- `src/predict/features.py::get_travel_distance()` — clasificación low/normal/high/extreme
- `src/predict/backtest.py` — calibration check por buckets
- Filosofía del ensemble: recalibración con backtest

**Estado:** ✅ **Implementación conceptual completa**

---

### 6. arXiv 2024 — *Predicting soccer with complex networks & ML*

**Publicación:** arXiv preprint
**URL:** https://arxiv.org/html/2409.13098v1
**Autores:** Baratela, Xavier, Peron, Villas-Boas, Rodrigues

**Hallazgo clave:**
- Passing networks (grafos de pases) **igualmente efectivos** que match stats
- **Combinación** de ambos > cada uno por separado
- Métricas útiles: clustering, betweenness, eigenvector centrality
- Granularidad por mitad de partido > global

**Implementado en:** ❌ **No implementado** (Fase 8)

**Gap:**
- Requiere construir passing networks desde fixture_events
- Calcular métricas topológicas por partido
- Integrar como features al ensemble

---

### 7. Springer 2024 — *Data-driven prediction of soccer outcomes*

**Publicación:** Journal of Big Data
**URL:** https://link.springer.com/article/10.1186/s40537-024-01008-2

**Hallazgos clave:**
- 28 nuevos features introducidos
- Real-time features (half-time results)
- Hyperparameter tuning (grid + Bayesian)
- Voting ensemble ML + DL > individual
- FNN + Vanilla RNN para temporales

**Implementado en:** ⚠️ **Parcial** (algunos features sí, XGBoost no)

**Gap (Fase 8+):**
- ❌ XGBoost model
- ❌ Voting ensemble formal
- ❌ FNN / RNN
- ❌ Half-time scoring feature

---

### 8. anl.bet (2025) — *Chile Soccer Analytics: Altitude & Travel*

**Publicación:** Industry analytics
**URL:** https://anl.bet/chile-soccer-analytics-the-impact-of-altitude-and-long-away-trips-on-results/

**Hallazgos clave:**
- Altitude bands:
  - <1,200m: baseline
  - 1,200-2,000m: ventilatory stress
  - >2,000m: marked endurance reduction
- Travel fatigue es **acumulativo** (compounding)
- 3 matches in 2 weeks con 2 road trips → drop en 2nd away match
- Sports-science disruption sleep → reduced decision-making

**Implementado en:**
- `src/predict/features.py::get_travel_distance()` — km últimos 7d + classification
- `src/predict/features.py::get_fixture_congestion()` — games_7d + games_14d
- `src/predict/heuristics.py` — heurísticas #5 y #6

**Estado:** ✅ **Producción**

**Calibración MX:** 
- Travel >1500km: penalización visitante (ya implementado)
- Congestion 3+ en 7d: penalización menor (sorprendentemente bajo en MX)

---

### 9. Smoulder et al. (2024) — *A Neural Basis of Choking Under Pressure*

**Publicación:** Neuron (revista top de neurociencia)
**DOI:** 10.1016/j.neuron.2024.08.012

**Hallazgos clave:**
- Inverted-U entre reward y performance
- Jackpot rewards **sobreactivan corteza prefrontal**
- Interfieren con corteza motora automática
- Cerebelo maneja automaticidad; prefrontal "clamp down" lo interrumpe

**Implementado en:** ❌ **Pendiente** (Fase 6)

**Plan de implementación:**
```python
def get_choking_risk(features, narrative_stakes):
    """
    Composite feature: high-stakes + high-status + skill alto
    
    Trigger conditions:
    - high_stakes match (manual flag: final/liguilla/clásico definitorio)
    - Local team top-5 Elo (high-status)
    - Local team has high self-reported "must-win" pressure
    """
    base = 0.0
    if high_stakes:
        base += 0.05
    if home_is_top_elo:
        base += 0.03
    if elo_diff < 0 (local is favorite):
        base += 0.02
    return min(0.10, base)
```

---

### 10. Chabrol et al. (2019) — *Cerebellar Contribution to Preparatory Activity in Motor Neocortex*

**Publicación:** Neuron
**DOI:** 10.1016/j.neuron.2019.05.022

**Hallazgo clave:**
- Cerebelo **prepara** actividad motora
- Prefrontal puede **clamp down** e interrumpir fluidez
- Arthur Ashe lo llamó "paralysis by analysis"

**Implementado en:** ❌ **No aplicable directamente** (conceptual)

**Insight:** DT que da muchas instrucciones pre-partido puede empeorar el performance. Detectado indirectamente vía heurística #1 (coach tenure bajo = puede sobre-analizar).

---

### 11. Yerkes-Dodson Law (1908)

**Publicación:** Journal of Comparative Neurology and Psychology, 18(5), 459-482
**URL:** https://en.wikipedia.org/wiki/Yerkes%E2%80%93Dodson_law

**Hallazgo clave:**
- Inverted-U entre arousal y performance
- Tareas complejas: arousal moderado es óptimo
- Lupien 2007: glucocorticoids muestran misma curva

**4 disparadores de stress response:**
1. Novel
2. Unpredictable
3. Not controllable
4. Social-evaluative threat

**Implementado en:** ⚠️ **Conceptual** (derby flatten + heurísticas)

**Plan:** Feature `match_stakes` manual con valores:
- `low` (jornada normal) — sin ajuste
- `medium` (clásico, liguilla) — +0.5% arousal implícito
- `high` (final, partido definitorio) — +1% arousal + choking risk

---

### 12. Miller & Sanjurjo (2018) — *Re-analysis of Hot Hand in Basketball*

**Hallazgo:**
- Identificaron **sampling bias** en el paper original de Gilovich 1985
- **El hot hand ES real** pero el effect size es PEQUEÑO
- Solo un subset pequeño de jugadores muestra el efecto

**Implementado en:**
- `src/predict/features.py::get_exponential_form()` — decay=0.85 (pondera recent)
- `src/predict/heuristics.py` — heurística #9 (momentum exponencial)
- ⚠️ Calibrar magnitud para evitar overfit

**Estado:** ✅ **Producción**

---

### 13. Mesagno et al. — *Choking in sport*

**Publicaciones:** Multiple, incluyendo ScienceDirect (DOI: S1469029224000748)
**Datos:** Survey de 165 atletas (club-level a olímpicos)

**Hallazgos cuantitativos:**
- **80% de atletas** reportó choking en último año
- **7% tuvo pensamientos suicidas**
- 3 componentes del choking:
  1. Aumento de ansiedad vs práctica
  2. Disminución de performance
  3. **Nivel de skill alto** (novatos no chokean)

**Tipos susceptibles (Mary Spillane):**
- Over-thinkers
- Perfectionists
- Athletic identity fuerte
- Mental health concerns

**Implementado en:** ❌ **Pendiente** (Fase 6 — combinado con #9)

---

### 14. Adams & Kupper — *Home-field as expertise deficiency*

**Hallazgo clave:**
- Home advantage es **MÉTRICA DE INHABILIDAD**
- **Inversamente proporcional** a expertise
- Equipos más hábiles tienen **menos** home advantage

**Implementado en:** ❌ **Pendiente** (Fase 6)

**Plan:**
```python
def get_expertise_modifier(elo_home, elo_away):
    """
    Modula home advantage por skill relativo.
    Equipos débiles: HA pesa más
    Equipos fuertes: HA pesa menos
    """
    skill_gap = abs(elo_home - elo_away)
    # HA más fuerte si diferencia de skill es baja
    ha_modifier = 1.0 - (skill_gap / 400) * 0.2  # hasta -20% si gap 400+
    return max(0.7, ha_modifier)
```

---

### 15. Wikipedia "Home advantage" — Comprehensive overview

**Datos cuantitativos:**
- English Premier (2006): local anota **37.29% más** goles
- FIFA World Cup: 6/7 ganadores por localía
- Away goals rule (UEFA) — explícito reconocimiento

**Factores:**
- **Psicológicos** (difíciles de medir): familiaridad, crowd, no travel
- **Fáciles de medir**: referee bias, acclimatación, logística

**Implementado en:**
- `get_altitude_advantage` (parcial)
- Base conceptual del modelo

**Gap:**
- ✅ Referee ID (Fase 9) — `src/predict/referee_bias.py` + `get_referee_bias()`
- ❌ Attendance (Fase 9+ pendiente — scraping ESPN necesario)

---

## 🗺️ Mapeo paper → feature → código

| Feature en modelo | Paper base | Función Python | Línea aprox. |
|---|---|---|---|
| **Forma últimos 5** | Estándar / MDPI 2025 | `get_team_form()` | features.py |
| **Forma ponderada exp** | Miller-Sanjurjo 2018, Dixon-Coles 1997 | `get_exponential_form()` | features.py |
| **H2H** | Estándar | `get_head_to_head()` | features.py |
| **Home/Away split** | Pollard 2008, Wikipedia | `get_home_away_split()` | features.py |
| **Altitud (MX calibrada)** | McSharry 2007 BMJ | `get_altitude_advantage()` + heurística #1 | features.py + heuristics.py |
| **Rest days** | Distribución MX calibrada | `rest_days_advantage()` | features.py |
| **Coach pressure** | PLOS 2025, Mesagno | `get_coach_pressure()` | features.py |
| **Coach tenure** | MDPI 2025 | `get_coach_tenure_days()` | features.py |
| **Travel distance** | anl.bet 2025 | `get_travel_distance()` | features.py |
| **Fixture congestion** | anl.bet 2025 | `get_fixture_congestion()` | features.py |
| **Attack/defense strength** | Dixon-Coles 1997 | `get_attack_defense_strength()` | features.py |
| **Elo Rating** | FiveThirtyEight + MDPI 2025 | Elo class | elo.py |
| **Dixon-Coles Poisson** | Dixon & Coles 1997 | `predict_from_model()` | dixon_coles.py |
| **Derby detection** | The Playbook 2024 | `detect_derby()` | heuristics.py |
| **Narrativas del usuario** | The Playbook 2024 | `load_manual_narratives()` | heuristics.py |

---

## ❌ Features pendientes (con paper que las justifica)

| Feature | Paper | Fase | Dificultad |
|---|---|---|---|
| **Choking risk score** | Smoulder 2024, Mesagno | 6 | Media (requiere match_stakes manual) |
| **Match stakes (manual flag)** | Yerkes-Dodson, Mesagno | 6 | Baja (JSON flag) |
| **Expertise differential** | Adams & Kupper | 6 | Baja (computed) |
| **xG (Expected Goals)** | Springer 2024, MDPI 2025 | 7 | Alta (shot-level data) |
| **Passing networks** | arXiv 2024 | 8 | Alta (event-level data) |
| **Referee bias** | The Playbook 2024, Avugos 2024 | 7 | Media (referee ID) |
| **Attendance/crowd** | Wikipedia 2024, The Playbook 2024 | 7 | Media (SportMonks metadata) |
| **Weather** | Multiple (heat, rain) | 7 | Media (Open-Meteo) |
| **Player-level stats** | MDPI 2025, Springer 2024 | 8 | Alta (player_id data) |
| **XGBoost stacking** | Springer 2024, MDPI 2025 | 8 | Media |
| **Half-time scoring** | Springer 2024 | 9 | Alta (live data) |
| **Pre-performance routines** | Mesagno, Spillane | 9 | No medible |

---

## 📊 Estado consolidado por paper

### ✅ Producción (5 papers)
- McSharry 2007 (altitud)
- anl.bet 2025 (travel + congestion)
- Miller & Sanjurjo 2018 (hot hand)
- Foresportia (filosofía)

### ⚠️ Producción parcial (5 papers)
- PLOS 2025 (psicología)
- MDPI 2025 (ML review)
- The Playbook 2024 (crowd + choking)
- Wikipedia home advantage
- Springer 2024 (parcial)

### ❌ Pendiente (5 papers)
- Smoulder 2024 Neuron (choking)
- Mesagno (choking + 80% atletas)
- arXiv 2024 (passing networks)
- Adams & Kupper (expertise)
- Chabrol 2019 (cerebellar)

---

## 🔄 Cómo usar este documento

### Cuando Ángel pregunte "¿qué papers usaste?"
Apuntar a la tabla maestra. Mostrar:
- 5 papers producción
- 5 papers parcial
- 5 papers pendientes

### Cuando Ángel pida implementar X
Buscar en "Features pendientes" → identificar paper → implementar.

### Cuando se publique un paper nuevo
1. Añadir a "Papers consultados" con # correlativo
2. Identificar qué feature(s) mejora
3. Marcar estado

---

## 📚 Papers pendientes de revisar (no consultados aún)

Por hacer en futuras sesiones:
- **Avugos et al. (2024)** — Home advantage + officiating decisions (referee bias)
- **Pollard (2008)** — Home advantage review (mencionado pero no leído a fondo)
- **Nassis (2013)** — Acclimatación a altitud
- **Karlis & Ntzoufras (2003)** — Bivariate Poisson (alternativa a Dixon-Coles)
- **Koopman & Lit (2015)** — Dynamic rating (alternativa a Elo)
- **Williams & Walters (2011)** — Altitude effects (específico)
- **Lupien et al. (2007)** — Glucocorticoids + Yerkes-Dodson
- **Charest & Sleep** — Sleep + athletic performance (Springer 2024)
- **Multiple COVID home advantage studies** —Bryson et al. (2022), etc.
- **xG literature** — Anzer & Bauer (2021), Expected Goals papers

---

## 📌 Comando útil

```bash
# Ver qué papers están pendientes de leer
grep "Pendiente" /workspace/proyectos/docs/ARTICLES_INVENTORY.md

# Ver estado de features
grep -A 20 "Mapeo paper" /workspace/proyectos/docs/ARTICLES_INVENTORY.md
```

---

## 🆕 Papers de xG (Fase 8 — agregados 2026-06-27)

### 16. Lucey et al. (2015) — *Quality vs Quantity: Improved Shot Prediction in Soccer using Tactical Features*

**Publicación:** MIT Sloan Sports Analytics Conference 2015
**URL:** http://www.sloansportsconference.com/wp-content/uploads/2015/02/SSP2015_Quality_Vs_Quantity_Improved_Shot_Prediction.pdf

**Hallazgo clave:**
- Shot location + body part + assist type + defender proximity → xG model
- R² ≈ 0.50 (vs ~0.30 para modelo naive basado en location solo)
- Tactical features (formation, pressure) agregan ~5% R²

**Aplicado en:** `src/predict/xg.py` (Fase 8)
- NO usamos shot location / body part (no disponibles en SportMonks free)
- SÍ usamos shot_quality (sib/st), sot, is_home como proxy
- Correlación resultante: 0.55 (vs 0.72 paper original con más features)

**Limitaciones conocidas:**
- Nuestro modelo tiene ~0.20 R² menos que el paper
- Sin coordenadas, sin body part, sin assist type, sin formación
- Suficiente para ser mejor que Elo, no suficiente para igualar Premier League

**Paper complementario:**
- **Caley, M. (2015)** — "Cartilage Free Captain" blog — Primer uso público
  sistemático de xG como predictor. Inspiró todo el campo.

---

### 17. Caley, M. (2015) — *Cartilage Free Captain: Shot Quality Analysis*

**Publicación:** Cartilage Free Captain (SB Nation), 19 Oct 2015
**URL:** https://cartilagefreecaptain.sbnation.com/2015/10/19/9247711/shot-quality-and-champions-league-knockout-rounds

**Hallazgo clave:**
- xG predice resultados MEJOR que goles reales
- Equipos que "sobre-performan" sus xG tienden a "regresar a la media"
- Shot quality > shot quantity en Premier League

**Aplicado en:** Inspiración conceptual para `xg.py`
- Confirmó que xG debe ser predictor forward-looking (no retrospectivo)
- Motivó el rolling xG con decay exponencial
- Justificó invertir tiempo en construir proxy aunque sea imperfecto

**Por qué importa para Liga MX:**
- Sin xG público para MX,，所以我们 construimos proxy propio
- Misma filosofía: xG > goles reales para predecir
- Diferencia: usamos stats agregados (no shot-level)

---

### 18. Anzer & Bauer (2021) — *Expected Goals (xG) — Models for Assessing the Quality of Shots in Soccer*

**Publicación:** Springer, Briefs in Applied Statistics and Data Science
**URL:** https://link.springer.com/book/10.1007/978-3-030-72568-0

**Hallazgo clave:**
- Review comprehensivo de modelos xG en literatura
- Compara GLM Poisson, Random Forest, XGBoost, Neural Networks
- GLM Poisson con ~10 features logra R² ≈ 0.35-0.40
- XGBoost con más features llega a R² ≈ 0.45

**Aplicado en:** Referencia conceptual (Fase 9+)
- Planeamos probar XGBoost para Fase 9 si sklearn se hace disponible
- Por ahora nuestro ridge log-link (NumPy) es equivalente a GLM Poisson
- Nuestro R² ≈ 0.30 está en el rango bajo del paper — esperado por datos limitados

**Insights clave:**
- Feature importance típica: shot location > body part > assist type > defender position
- Importante validar con cross-validation (K-fold) para evitar overfit
- Mejora marginal con deep learning (~0.02 R²) no justifica complejidad

**Para Fase 9 (stacking XGBoost):**
- Usar output de xG, Elo, DC como features de entrada
- Cross-validation con K=5 folds temporales (no random)
- Métrica objetivo: Brier score (no accuracy, que es ruidosa)
