# 🔍 Auditoría de Fuentes de Datos — SportMonks + Scraping

> **Fecha:** 2026-06-26
> **Objetivo:** Documentar exactamente qué cubre SportMonks v3 (plan custom de Ángel) vs qué necesitamos obtener por otras fuentes.

---

## ✅ Lo que SÍ cubre SportMonks v3 (Custom Plan)

### Endpoints que respondieron correctamente (verificados en vivo):

| Endpoint | Status | Datos que trae |
|---|---|---|
| `leagues/{id}` | ✅ | Info de liga, país |
| `leagues/{id}?include=seasons` | ✅ | Temporadas (2005-2026) |
| `seasons/{id}?include=fixtures.*` | ✅ | TODOS los fixtures con includes |
| `fixtures/{id}?include=metadata` | ✅ | **formations, attendance, kits** |
| `fixtures/{id}?include=lineups.player` | ✅ | Alineaciones con jugador completo |
| `fixtures/{id}?include=lineups.position` | ✅ | Posición del jugador |
| `fixtures/{id}?include=lineups.details` | ✅ | Stats detalladas por jugador en partido |
| `fixtures/{id}?include=scores;events;statistics.type` | ✅ | Resultado, eventos, stats con nombres |
| `fixtures/{id}?include=trends` | ✅ | Time-series (posesión por minuto, etc.) |
| `fixtures/{id}?include=pressure` | ✅ | Pressure Index time-series |
| `coaches` | ✅ | 285+ coaches con altura, peso, fecha nac |
| `coaches/{id}?include=teams` | ✅ | Historial DT×equipo×fechas |
| `teams/{id}?include=squad` | ✅ | Roster del equipo |
| `teams/{id}?include=players` | ✅ | Jugadores con detail |
| `players/{id}` | ✅ | Datos físicos del jugador |
| `referees` | ✅ | Lista de árbitros |
| `referees/seasons/{id}` | ✅ | Árbitros por temporada |
| `transfers` | ✅ | Transferencias (from, to, date, amount) |
| `transfers/teams/{id}` | ✅ | Transferencias por equipo |
| `standings/seasons/{id}` | ✅ | Tabla de posiciones por temporada |
| `topscorers/seasons/{id}` | ✅ | Goleadores con player+team incluido |
| `schedules/seasons/{id}` | ✅ | Calendario de la temporada |
| `rounds/seasons/{id}?include=fixtures` | ✅ | Rounds con fixtures incluidos |
| `stages/seasons/{id}` | ✅ | Fases del torneo |
| `livescores/inplay` | ✅ | Resultados en vivo |

### 🎁 Cosas valiosas que NO sabía:
- **Metadata de fixture incluye formations** (4-2-3-1, 4-4-2, etc.) ← CRÍTICO para modelo
- **Metadata incluye attendance** (31,651 en un partido) ← Dato difícil de conseguir
- **Lineups.detail trae stats por jugador** (no solo si jugó) ← Rating individual por partido
- **Trends y pressure** son time-series ← Para análisis de momentum

---

## ❌ Lo que NO cubre SportMonks (gaps a resolver)

### Gaps críticos (afectan features del modelo):

| Dato | ¿Por qué falta? | Solución propuesta |
|---|---|---|
| **Weather histórico** | No hay endpoint | **Open-Meteo Historical Weather API** (gratis, sin key) |
| **Coach tactical_style** | No hay campo en SportMonks | **Manual + scraping Transfermarkt** |
| **Coach formation_preference** | No hay campo | **Manual + scraping** |
| **Stadium surface/roof_type** | No viene en venue | **Manual** (solo ~30 estadios Liga MX) |
| **Derbies / clásicos** | No hay endpoint | **JSON estático** (ya está en `db.py`) |
| **Match context (presión)** | No scrapeable | **Manual / heurística** desde forma reciente |
| **Player injuries** | No hay endpoint dedicado | **Scraping ESPN MX** o **manual** |

### Gaps menores (opcional / nice-to-have):

| Dato | Solución |
|---|---|
| **News** (artículos) | Plan no incluye `/news`. Usar Google News RSS como alternativa |
| **Predictions AI** | Add-on de pago (€15/mes). Por ahora lo calculamos nosotros |
| **xG** | Add-on de pago (€24/mes). Calcular con xGProxy desde stats si lo necesitamos |
| **Match Facts (beta)** | Plan no incluye. Usar `metadata` + `lineups.details` |

---

## 🌤️ Plan de Weather (Open-Meteo)

**API gratuita**, sin key, histórico desde 1940.

```python
# Open-Meteo Archive API
GET https://archive-api.open-meteo.com/v1/archive
    ?latitude=19.3029&longitude=-99.1505
    &start_date=2024-02-26
    &end_date=2024-02-26
    &hourly=temperature_2m,relativehumidity_2m,precipitation,windspeed_10m,weathercode
```

**Estimación:** 3,081 fixtures × 1 call = 3,081 calls (gratis, sin rate limit agresivo).

**Datos a obtener por partido:**
- `temperature_2m` (°C a la hora del partido)
- `feels_like_2m` (calculable)
- `relativehumidity_2m` (% humedad)
- `precipitation` (mm de lluvia)
- `windspeed_10m` (km/h viento)
- `weathercode` (código WMO: despejado, lluvia, etc.)

---

## 📊 Plan de Scraping para datos manuales

### Fuentes candidatas:

1. **Transfermarkt** (https://www.transfermarkt.com)
   - ✅ Tactical style del DT (4-3-3 attack, defensive, etc.)
   - ✅ Formación preferida
   - ✅ Lesiones (con fechas)
   - ⚠️ Requiere respeto a robots.txt / User-Agent

2. **ESPN MX** (https://www.espn.com.mx/futbol/)
   - ✅ Lesiones de jugadores MX
   - ✅ Notas previas al partido (presión, momento)
   - ⚠️ Estructura HTML cambia frecuentemente

3. **Wikipedia**
   - ✅ Stadium details (superficie, techo)
   - ✅ Histórico de los clubes
   - ✅ Gratis, pero requiere parser

4. **FBref** (https://fbref.com)
   - ✅ Stats avanzadas (xG calculado)
   - ✅ Datos de jugadores detallados
   - ⚠️ Anti-scraping fuerte

5. **Medios mexicanos**: ESPN MX, TUDN, Récord, MedioTiempo
   - ✅ Notas de prensa previas al partido
   - ✅ Estado anímico de jugadores / DT
   - ⚠️ NLP necesario para extraer info útil

---

## 📋 Plan de implementación por fases

### ✅ Fase 1 (COMPLETADA - hoy)
- Schema v2 + migración + ingestas iniciales
- 285 coaches, 1,082 tenures, 127,186 lineups, 2,492 players, 45 venues

### 🔄 Fase 2 (mañana) - Datos scrapeable que faltan

| Script | Tarea | Tiempo |
|---|---|---|
| `ingest_metadata.py` | Extraer formations + attendance de cada fixture | 30 min |
| `ingest_referees.py` | Referees (árbitros) por temporada | 30 min |
| `ingest_transfers.py` | Transfers por equipo (10 temporadas × 47 equipos) | 1-2h |
| `ingest_standings.py` | Standings + Topscorers por temporada | 1h |
| `ingest_weather.py` | Weather histórico vía Open-Meteo (3,081 fixtures) | 2-3h |

### 📝 Fase 3 (después) - Datos manuales + cálculo

| Script | Tarea | Tiempo |
|---|---|---|
| `enrich_coaches_tactics.py` | JSON manual para tactical_style, formation | 30 min |
| `enrich_venues_advanced.py` | Stadium surface/roof_type (manual) | 30 min |
| `compute_team_form.py` | team_form desde fixtures existentes | 1h |
| `compute_player_form.py` | player_form desde lineups | 1-2h |
| `compute_coach_form.py` | coach_form desde tenures + fixtures | 1h |
| `compute_match_context.py` | match_context (derby, descanso, consecutivos) | 1h |
| `compute_travel_log.py` | travel_log (distancia desde venue anterior) | 1h |

### 🤖 Fase 4 (opcional) - Scraping avanzado

| Script | Fuente | Riesgo |
|---|---|---|
| `scrape_transfermarkt.py` | Transfermarkt | Anti-bot, requiere proxy |
| `scrape_fbref.py` | FBref | Rate-limited |
| `scrape_espn_injuries.py` | ESPN MX | Cambia HTML |

---

## 🎯 Resumen ejecutivo para Ángel

| Categoría | Cantidad | % |
|---|---|---|
| ✅ Datos scrapeables de SportMonks (ya en BD) | 250K+ registros | 75% |
| 🟡 Datos scrapeables de SportMonks (pendientes) | ~50K registros | 15% |
| 🟠 Datos de APIs externas (Open-Meteo) | 3,081 fixtures | 5% |
| 🔴 Datos manuales (psicología, táctica) | ~50 entradas | 5% |

**El 90% de los datos los podemos automatizar.**
**El 10% restante requiere curación humana** (psicología, contexto especial).

---

## 💡 Recomendaciones

1. **SportMonks custom plan está bien usado.** Aprovechemos formations, attendance, lineups.details, transfers, referees, standings, topscorers, rounds — todo GRATIS.

2. **Open-Meteo para weather.** Gratis, sin key, histórico bueno. Solo ~3K calls.

3. **Datos manuales vía JSON/YAML.** Te armo un archivo `data/manual/` donde tú puedas ir agregando:
   - `derbies_liga_mx.json` (ya existe el dict en db.py)
   - `coach_tactics.json` (DT × tactical_style × formation)
   - `stadium_surface.json` (venue_id → surface/roof)
   - `team_context.json` (presiones especiales de la temporada)

4. **Scraping solo si lo necesitamos.** Para Liga MX hay fuentes decentes (ESPN MX, Wikipedia) pero hay que ser cuidadosos con rate limits y ToS.

5. **El modelo ML funcionará aún sin weather y sin manual.** Tenemos:
   - 192K stats de partido
   - 127K lineups con rating
   - 285 coaches con historial
   - 3,081 fixtures con resultado
   - 44 venues con altitud real

**Suficiente para un baseline sólido.**

---

## 🔐 Privacidad y respeto

- Todos los tokens en `.env` con permisos 600
- No publicar el token en logs ni commits
- Para scraping: User-Agent identificable, respeto a robots.txt, rate limiting 1 req/seg
- Open-Meteo: solo usar hasta 10K requests/día según sus ToS