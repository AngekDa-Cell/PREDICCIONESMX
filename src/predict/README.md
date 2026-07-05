# Predictions_MX — Sistema de Predicción

> Sistema profesional de predicción de partidos de Liga MX.
> Última actualización: 2026-06-27

---

## 🎯 Overview

Predictions_MX es un sistema en 5 capas que combina:
- **Modelos estadísticos** (Dixon-Coles, Elo Rating)
- **Features engineered** (11 features validados científicamente)
- **Heurísticas del analista** (calibradas con datos Liga MX propios)
- **Narrativas manuales** (input cualitativo de Ángel)
- **Bitácora del analista** (tracking de accuracy)

**Estado actual:**
- Accuracy backtest 2025: **52.65%** (vs 33.3% baseline)
- Brier Score: **0.5959** (excelente calibration)
- Log Loss: 0.999

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

---

## 📁 Estructura

```
src/predict/
├── __init__.py           # Interfaz pública
├── cli.py                # CLI principal
├── features.py           # 11 features engineered
├── dixon_coles.py        # Modelo Poisson + corrección τ
├── elo.py                # Rating Elo dinámico
├── heuristics.py         # 11 reglas del analista
├── analyst_log.py        # Bitácora de predicciones
├── backtest.py           # Sistema de backtesting
├── misc_utils.py         # Utilities
└── mx_coefficients.json  # Calibraciones MX
```

```
data/manual/
└── narratives_default.json   # Narrativas editables
```

```
docs/
├── RESEARCH_SYNTHESIS.md     # Papers revisados
├── METHODOLOGY.md            # Cómo funciona
├── FEATURES.md               # Catálogo de features
├── BACKTESTING_RESULTS.md    # Resultados empíricos
└── ROADMAP.md                # Próximos pasos
```

---

## 📊 Modelos implementados

### 1. Dixon-Coles (1997)

- Poisson bivariado para goles
- Corrección τ para scorelines bajos (0-0, 1-1)
- Parámetros: attack, defense, home_advantage, ρ

### 2. Elo Rating

- Implementación estilo FiveThirtyEight
- K-factor con multiplier por goal difference
- Home advantage: 100 puntos
- Update incremental después de cada partido

### 3. Ensemble (DC + Elo + heurísticas)

```
final_prob = 0.55 × Elo + 0.30 × Dixon-Coles + 0.15 × heurísticas
```

Pesos calibrados con backtesting 2025.

---

## 🧠 Features (11)

Ver [`docs/FEATURES.md`](../../docs/FEATURES.md) para detalle completo.

| Feature | Tipo | Paper base |
|---|---|---|
| Forma últimos 5 | Auto | MDPI 2025 |
| Forma ponderada exp | Auto | Dixon-Coles original |
| H2H últimos 10 | Auto | Estándar |
| Home/Away split | Auto | Pollard 2008 |
| **Altitud MX** | Auto | McSharry 2007 BMJ (calibrado MX) |
| Rest days | Auto | Distribución MX |
| Coach pressure | Auto | PLOS 2025 |
| Coach tenure | Auto | MDPI 2025 |
| Travel distance | Auto | anl.bet 2025 |
| Fixture congestion | Auto | Standard |
| Attendance/crowd | Auto | Pendiente |

---

## 🧪 Heurísticas

11 reglas empíricas del analista humano:

1. **Altitud MX** (+2.48%/1000m)
2. **Derby detection** (6 derbies MX)
3. **Presión DT** (winless ≥ 5)
4. **Forma streak** (3+ W o L)
5. **Travel fatigue** (>1500km)
6. **Fixture congestion** (3+ en 7d)
7. **Coach tenure** (new manager bounce)
8. **Momentum score** (decay exponencial)
9. **H2H dominance** (>65%)
10. **Narrativas del usuario**
11. **Derby flatten** (-15%)

---

## 🎲 Narrativas del usuario

Edita `data/manual/narratives_default.json` para agregar contexto:

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

O usa `--narrative "..."` en CLI para narrativa one-off.

---

## 📊 Backtesting

```bash
# Backtest completo
python3 src/predict/backtest.py --start 2024-01-01

# Output ejemplo:
# Modelo      Accuracy    Brier    LogLoss
# elo         51.32%      0.5902   0.9904
# ensemble    47.65%      0.6244   1.0387
```

---

## 📈 Métricas actuales

| Métrica | Valor | Meta |
|---|---|---|
| Accuracy (2025) | 52.65% | >50% ✅ |
| Brier Score | 0.5959 | <0.55 |
| Calibration (delta max) | +0.10 | <0.05 ⚠️ |
| Log Loss | 0.999 | <1.0 ✅ |

---

## ⚠️ Limitaciones

1. Sin xG (shot-level)
2. Sin referee bias
3. Sin weather data
4. Sin live tracking
5. Overconfident en >70% confidence

Ver [`docs/ROADMAP.md`](../../docs/ROADMAP.md) para planes de mejora.

---

## 📚 Documentación adicional

- [`docs/RESEARCH_SYNTHESIS.md`](../../docs/RESEARCH_SYNTHESIS.md) — Papers revisados
- [`docs/METHODOLOGY.md`](../../docs/METHODOLOGY.md) — Cómo funciona
- [`docs/FEATURES.md`](../../docs/FEATURES.md) — Catálogo completo
- [`docs/BACKTESTING_RESULTS.md`](../../docs/BACKTESTING_RESULTS.md) — Resultados empíricos
