"""
heuristics.py — Capa de heurísticas del "analista humano".

Aquí hidupan las reglas empíricas que un scout profesional reconocería:
- patterns históricos difíciles de cuantificar
- ajustes por tipo de partido (derby, final, cierre de temporada)
- " sentido común" Deportivo basado en contexto MX
"""

import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# KNOWN PATTERNS — Liga MX
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_PATTERNS = {
    # "Equipo local conDT nuevo en primeros 3 partidos" → reduce local advantage
    "new_coach_home_debut": {
        "condition": "home_coach_first_3_games",
        "direction": "reduce_home_win",
        "magnitude": 0.08,  # reduce ~8% la probabilidad de victoria local
        "reason": "DT nuevo aún implementando sistema, especialmente visitante en debut"
    },

    # "Equipo que no gana en 5+ partidos" → pressure builds, especially away
    "winless_5_plus": {
        "condition": "winless_streak >= 5",
        "direction": "reduce_away_win_if_visitor",
        "magnitude": 0.10,
        "reason": "Sequía de victorias genera ansiedad, sobre todo lejos de casa"
    },

    # "Llegar cansado de racha de 3 partidos en 10 días"
    "compressed_schedule": {
        "condition": "rest_days < 3",
        "direction": "reduce_both_attacks",
        "magnitude": 0.07,
        "reason": "Fatiga acumulada reduce calidad de ejecución técnica"
    },

    # "Altitud > 2400m contra equipo costero" → ventaja exagerada
    "high_altitude_advantage": {
        "condition": "home_altitude >= 2400 AND away_altitude < 100",
        "direction": "boost_home_win",
        "magnitude": 0.12,
        "reason": "Diferencia de altitud extrema (CDMX/Toluca/Pachuca vs Tijuana/Santos)"
    },

    # "H2H claramente asimétrico en últimos 10" → pattern deBook
    "h2h_dominant": {
        "condition": "h2h_win_rate > 0.65 OR h2h_win_rate < 0.35",
        "direction": "boost_direction",
        "magnitude": 0.09,
        "reason": "Patrón histórico de dominio en el head-to-head"
    },

    # "Último partido fue derrota dolorosa (4+ diferencia)"
    "heavy_loss_previous": {
        "condition": "previous_loss_margin >= 4",
        "direction": "reduce_win_prob_next",
        "magnitude": 0.06,
        "reason": "Derrota abultada genera efecto psicológico de baja moral"
    },

    # "Derby / Clásico" → todo se sale de los números
    "is_classic": {
        "condition": "is_derby = True",
        "direction": "flatten_probabilities",
        "magnitude": 0.15,
        "reason": "Clásicos son impredecibles; la rivalidad elimina efecto de rankings"
    },

    # "Partido de cierre de temporada (jornada 17+)" → más empates
    "season_end": {
        "condition": "matchday >= 16",
        "direction": "boost_draw",
        "magnitude": 0.07,
        "reason": "Equipos con posiciones definidas juegan con menos intensidad"
    },

    # "Liguilla / playoff" → local advantage sube
    "playoff": {
        "condition": "is_playoff = True",
        "direction": "boost_home_win",
        "magnitude": 0.10,
        "reason": "En liguilla la localía pesa más; todo se decide en detalles"
    },

    # "Equipo en zona de descenso contra equipo sin presión"
    "relegation_battle": {
        "condition": "home_relegation_zone OR away_relegation_zone",
        "direction": "boost_home_if_home_in_zone",
        "magnitude": 0.08,
        "reason": "Equipo en descenso juega con desesperación; puede dar sorpresa"
    },
}


def load_manual_narratives(season: str = "current") -> Dict[str, Any]:
    """Carga narratives JSON editadas por Ángel."""
    base = Path(os.environ.get("PREDICCIONES_DATA_DIR", Path(__file__).resolve().parent.parent.parent / "data" / "manual"))
    files = [
        base / f"narratives_{season}.json",
        base / "narratives_default.json",
    ]
    for fpath in files:
        if fpath.exists():
            with open(fpath) as f:
                return json.load(f)
    return {"season": season, "narratives": [], "derbies": [], "warnings": []}


def detect_derby(home_team: str, away_team: str) -> Optional[Dict[str, Any]]:
    """Detecta si es un clásico/derby conocido."""

    # Mapeo de equipos por apodo
    TEAM_ALIASES = {
        'américa': ['américa', 'las águilas', 'club américa'],
        'chivas': ['guadalajara', 'chivas', 'el rebaño', 'club guadalajara'],
        'cruz azul': ['cruz azul', 'la máquina', 'cemento'],
        'pumas': ['pumas', 'pumas unam', 'los pumas'],
        'toros': ['tijuana', 'toros', 'xolos'],
        'atlas': ['atlas', 'los rojinegros'],
        'león': ['león', 'los esmeraldas'],
        'tigres': ['tigres', 'tigres uanl', 'los tigers'],
        'rayados': ['monterrey', 'rayados', 'club monterrey'],
        'santos': ['santos', 'santos laguna', 'los guerreros'],
        'pachuca': ['pachuca', 'los tuzos'],
        'toluca': ['toluca', 'los chuecos'],
        'necaxa': ['necaxa', 'los rayos'],
        'san luis': ['atlético san luis', 'san luis'],
        'juárez': ['juárez', 'fc Juárez', 'los bravos'],
        'querétaro': ['querétaro', 'gallos', 'club querétaro'],
        'puebla': ['puebla', 'la franjirilla'],
        'mazatlán': ['mazatlán', 'mazatlán fc'],
    }

    def normalize(name: str) -> str:
        return name.lower().strip()

    def get_alias_set(name: str) -> set:
        n = normalize(name)
        for key, aliases in TEAM_ALIASES.items():
            if n in aliases or n == key:
                return set(aliases)
        return {n}

    home_set = get_alias_set(home_team)
    away_set = get_alias_set(away_team)

    # Clásicos MX reconocidos
    CLASSICS = [
        # Nombre, [aliases equipo A], [aliases equipo B], peso (0-1)
        ("Clásico Nacional", ['américa'], ['chivas', 'guadalajara'], 1.0),
        ("Clásico Tapatío", ['guadalajara', 'chivas'], [' atlas', 'atlas'], 0.8),
        ("Clásico Regio", ['monterrey', 'rayados'], ['tigres', 'tigres uanl'], 0.95),
        ("Clásico capitalino", ['américa'], ['pumas', 'pumas unam'], 0.9),
        ("Clásico de la Minerda", ['santos', 'santos laguna'], ['pachuca', 'pachuca'], 0.7),
        ("Clásico Azulgrana", ['cruz azul'], ['améica', 'club américa'], 0.85),
        ("Clásico joven", ['améica'], ['pumas', 'pumas unam'], 0.85),
    ]

    for classic_name, a_aliases, b_aliases, weight in CLASSICS:
        a_set = set(a_aliases); b_set = set(b_aliases)
        if (home_set & a_set and away_set & b_set) or \
           (home_set & b_set and away_set & a_set):
            return {
                "name": classic_name,
                "weight": weight,
                "description": f"Partido de alto voltaje emocional. El {classic_name} elimina mucho del análisis puramente estadístico."
            }

    return None


def apply_heuristics(
    features: Dict[str, Any],
    narratives: Dict[str, Any],
    model_output: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Ajusta las probabilidades del modelo Dixon-Coles
    con capas de heurísticas del analista humano.

    Returns:
        probabilities ajustadas + layer de explicación.
    """
    home_win = model_output['home_win']
    draw = model_output['draw']
    away_win = model_output['away_win']

    adjustments = []
    confidence_penalty = 1.0

    # Cargar coeficientes calibrados MX
    mx_coeffs = features.get('mx_coefficients', {})
    alt_coef = mx_coeffs.get('altitude', {})

    # ── 1. ALTITUD CALIBRADA CON DATOS MX ─────────────────────────────────
    alt = features.get('altitude', {})
    home_alt = alt.get('home_altitude', 0) or 0
    away_alt = alt.get('away_altitude', 0) or 0
    delta_alt = home_alt - away_alt  # metros de ventaja local

    # Coeficientes calibrados: +2.48% win rate por 1000m, +0.088 GD por 1000m
    # McSharry sugería +12% pero en MX el efecto es ~5x menor
    altitude_win_boost = (delta_alt / 1000.0) * 0.0248  # ±0.05 típicamente

    if abs(delta_alt) >= 1000:  # Solo ajustar si diferencia >= 1000m
        # Aplicar boost a home_win
        old_home = home_win
        home_win += altitude_win_boost * (1 - home_win) * 0.6
        away_win -= altitude_win_boost * away_win * 0.3
        adjustments.append({
            'type': 'altitude_mx_calibrated',
            'direction': 'favor_home' if delta_alt > 0 else 'favor_away',
            'magnitude': round(abs(altitude_win_boost), 4),
            'reason': f"ΔAltitud={delta_alt:+.0f}m. McSharry (Sudamérica): +12%/1000m. MX calibrado: +{abs(altitude_win_boost*100):.1f}%/1000m (efecto ~5× menor en MX)."
        })
        confidence_penalty *= 0.95

    # ── 2. TRAVEL DISTANCE (Fatiga acumulada por viaje) ──────────────────────
    home_travel = features.get('home_travel', {})
    away_travel = features.get('away_travel', {})
    home_dist = home_travel.get('distance_7d_km', 0)
    away_dist = away_travel.get('distance_7d_km', 0)

    if away_dist > 1500:  # Visitante con mucho viaje en últimos 7 días
        travel_penalty = min(0.08, away_dist / 30000)
        away_win -= travel_penalty * away_win
        home_win += travel_penalty * home_win * 0.5
        adjustments.append({
            'type': 'travel_fatigue',
            'direction': 'reduce_away_win',
            'magnitude': round(travel_penalty, 4),
            'reason': f"Visitante ha viajado {away_dist:.0f}km en últimos 7 días. Fatiga acumulada reduce performance."
        })
        confidence_penalty *= 0.92

    if home_dist > 1500:
        travel_penalty = min(0.06, home_dist / 30000)
        home_win -= travel_penalty * home_win
        adjustments.append({
            'type': 'home_travel_fatigue',
            'direction': 'reduce_home_win',
            'magnitude': round(travel_penalty, 4),
            'reason': f"Local ha viajado {home_dist:.0f}km en últimos 7 días."
        })
        confidence_penalty *= 0.94

    # ── 3. FIXTURE CONGESTION (3+ partidos en 7 días) ────────────────────────
    home_cong = features.get('home_congestion', {})
    away_cong = features.get('away_congestion', {})

    if away_cong.get('high_congestion', False):
        cong_penalty = 0.05
        away_win -= cong_penalty * away_win
        home_win += cong_penalty * home_win * 0.4
        adjustments.append({
            'type': 'visitor_congestion',
            'direction': 'reduce_away_win',
            'magnitude': cong_penalty,
            'reason': f"Visitante con {away_cong.get('games_7d', 0)} partidos en últimos 7 días. Riesgo de rotación/fatiga."
        })
        confidence_penalty *= 0.93

    if home_cong.get('high_congestion', False):
        cong_penalty = 0.04
        home_win -= cong_penalty * home_win
        adjustments.append({
            'type': 'home_congestion',
            'direction': 'reduce_home_win',
            'magnitude': cong_penalty,
            'reason': f"Local con {home_cong.get('games_7d', 0)} partidos en últimos 7 días."
        })
        confidence_penalty *= 0.95

    # ── 4. COACH TENURE / NEW COACH BOUNCE ──────────────────────────────────
    home_coach_t = features.get('home_coach_tenure', {})
    away_coach_t = features.get('away_coach_tenure', {})

    # New coach bounce: DT nuevo < 30 días → +5% resultado (promedio)
    if home_coach_t.get('is_new_coach', False):
        bounce = 0.05
        home_win += bounce * (1 - home_win) * 0.5
        adjustments.append({
            'type': 'home_new_coach_bounce',
            'direction': 'favor_home',
            'magnitude': bounce,
            'reason': f"DT nuevo ({home_coach_t.get('tenure_days', 0)} días). 'New manager bounce' típico +5% resultado."
        })
        confidence_penalty *= 0.88  # Bounce es inestable
    elif home_coach_t.get('phase') == 'established' and home_coach_t.get('win_rate', 0) > 0.55:
        stability = 0.03
        home_win += stability * (1 - home_win) * 0.4
        adjustments.append({
            'type': 'home_coach_stability',
            'direction': 'favor_home',
            'magnitude': stability,
            'reason': f"DT establecido ({home_coach_t.get('tenure_days', 0)} días) con WR={home_coach_t.get('win_rate', 0):.0%}."
        })

    if away_coach_t.get('is_new_coach', False):
        bounce = 0.05
        away_win += bounce * (1 - away_win) * 0.5
        adjustments.append({
            'type': 'away_new_coach_bounce',
            'direction': 'favor_away',
            'magnitude': bounce,
            'reason': f"DT visitante nuevo ({away_coach_t.get('tenure_days', 0)} días). 'New manager bounce'."
        })
        confidence_penalty *= 0.88

    # ── 5. MOMENTUM SCORE (forma ponderada exponencialmente) ────────────────
    home_exp = features.get('home_exp_form', {})
    away_exp = features.get('away_exp_form', {})

    home_momentum = home_exp.get('momentum_score', 1.5)
    away_momentum = away_exp.get('momentum_score', 1.5)

    momentum_diff = home_momentum - away_momentum

    if abs(momentum_diff) > 0.6:  # Diferencia significativa
        mom_adj = min(0.08, abs(momentum_diff) * 0.06)
        if momentum_diff > 0:
            home_win += mom_adj * (1 - home_win) * 0.5
            adjustments.append({
                'type': 'home_momentum',
                'direction': 'favor_home',
                'magnitude': round(mom_adj, 4),
                'reason': f"Local momentum_score={home_momentum:.2f} vs visitante={away_momentum:.2f}. Forma exponencial favorece local."
            })
        else:
            away_win += mom_adj * (1 - away_win) * 0.5
            adjustments.append({
                'type': 'away_momentum',
                'direction': 'favor_away',
                'magnitude': round(mom_adj, 4),
                'reason': f"Visitante momentum_score={away_momentum:.2f} vs local={home_momentum:.2f}."
            })

    # ── 5b. COMPOSITE MOMENTUM (Fase 6) — combina recent + exponential + trend ───
    home_comp = features.get('home_composite_momentum', {})
    away_comp = features.get('away_composite_momentum', {})

    if home_comp and away_comp:
        home_composite = home_comp.get('composite_score', 1.5)
        away_composite = away_comp.get('composite_score', 1.5)
        composite_diff = home_composite - away_composite

        # Si diferencia significativa en momentum compuesto (>0.5)
        if abs(composite_diff) > 0.5:
            comp_adj = min(0.06, abs(composite_diff) * 0.05)

            # Bonus por trend: si está mejorando Y tiene momentum alto, boost extra
            home_trend = home_comp.get('trend', 0)
            away_trend = away_comp.get('trend', 0)

            if composite_diff > 0:
                # Home tiene mejor momentum compuesto
                home_win += comp_adj * (1 - home_win) * 0.5
                reason_parts = [
                    f"Local composite_score={home_composite:.2f} vs visitante={away_composite:.2f}"
                ]
                if home_trend == 1:
                    reason_parts.append("tendencia ↗")
                if home_comp.get('consistency', 0) > 0.7:
                    reason_parts.append("alta consistencia")
                adjustments.append({
                    'type': 'home_composite_momentum',
                    'direction': 'favor_home',
                    'magnitude': round(comp_adj, 4),
                    'reason': '. '.join(reason_parts) + ".",
                })
            else:
                # Away tiene mejor momentum compuesto
                away_win += comp_adj * (1 - away_win) * 0.5
                reason_parts = [
                    f"Visitante composite_score={away_composite:.2f} vs local={home_composite:.2f}"
                ]
                if away_trend == 1:
                    reason_parts.append("tendencia ↗")
                if away_comp.get('consistency', 0) > 0.7:
                    reason_parts.append("alta consistencia")
                adjustments.append({
                    'type': 'away_composite_momentum',
                    'direction': 'favor_away',
                    'magnitude': round(comp_adj, 4),
                    'reason': '. '.join(reason_parts) + ".",
                })

        # Penalización por inconsistencia extrema
        home_consistency = home_comp.get('consistency', 0.5)
        away_consistency = away_comp.get('consistency', 0.5)

        if min(home_consistency, away_consistency) < 0.25:
            # Ambos equipos muy inconsistentes → baja confianza
            confidence_penalty *= 0.92
            adjustments.append({
                'type': 'low_consistency',
                'direction': 'reduce_confidence',
                'magnitude': 0.08,
                'reason': f"Ambos equipos con consistencia <0.25 (H={home_consistency:.2f}, A={away_consistency:.2f}). Forma volátil.",
            })

    # ── 5c. WEATHER (Fase 6) — clima del partido ──────────────────────────────────
    weather = features.get('weather', {})
    if weather.get('available'):
        # Calor extremo (>32°C) → FAVORECE AL VISITANTE (hallazgo backtest 2024-2026)
        # Realidad: en calor extremo, el visitante mejor preparado físicamente aprovecha;
        # local habituado pero visitante con mejor rotación de plantilla resiste más.
        # Calibrado con 1510 fixtures Liga MX: home win 37.8% en extremo vs 47.4% templado.
        if weather.get('is_extreme_heat'):
            adjustments.append({
                'type': 'extreme_heat',
                'direction': 'favor_away',
                'magnitude': 0.05,
                'reason': f"Calor extremo ({weather['temperature_c']:.1f}°C). Backtest muestra ventaja visitante en calor >32°C.",
            })
            away_win += 0.05 * (1 - away_win) * 0.5
            home_win -= 0.04 * home_win

        # Frío extremo (<15°C) → favorece visitante también (visitante adaptado mejor a clima controlado)
        if weather.get('temperature_c', 20) < 15:
            adjustments.append({
                'type': 'extreme_cold',
                'direction': 'favor_away',
                'magnitude': 0.08,
                'reason': f"Frío ({weather['temperature_c']:.1f}°C). Backtest: visitante gana 75% en <15°C (muestra pequeña).",
            })
            away_win += 0.08 * (1 - away_win) * 0.5

        # Alta humedad (>80%) → menos goles esperados, más draws
        if weather.get('is_high_humidity'):
            adjustments.append({
                'type': 'high_humidity',
                'direction': 'reduce_overall',
                'magnitude': 0.015,
                'reason': f"Humedad alta ({weather['humidity_pct']}%). Condiciones pesadas, juego más lento.",
            })
            center = (home_win + away_win) / 2
            home_win -= 0.01 * (home_win - center)
            away_win -= 0.01 * (away_win - center)

        # Tormenta severa (>10mm) → backtest muestra home win 51.1%, ligero advantage local
        if weather.get('precipitation_mm', 0) >= 10:
            adjustments.append({
                'type': 'severe_storm',
                'direction': 'favor_home',
                'magnitude': 0.03,
                'reason': f"Tormenta severa ({weather['precipitation_mm']:.1f}mm). Local gana 51% en tormentas.",
            })
            home_win += 0.03 * (1 - home_win) * 0.5

        # Lluvia ligera (>0.5mm) → penalizar confianza (más varianza)
        if weather.get('is_wet') and weather.get('precipitation_mm', 0) < 10:
            adjustments.append({
                'type': 'wet_conditions',
                'direction': 'reduce_confidence',
                'magnitude': 0.03,
                'reason': f"Lluvia ({weather['precipitation_mm']:.1f}mm). Superficie resbaladiza, más varianza.",
            })
            confidence_penalty *= 0.97

    # ── 5d. ATTENDANCE RATIO (Fase 9) — apoyo del público ──────────────────────
    # HALLAZGO BACKTEST (1,221 partidos Liga MX 2022-2025):
    #   Estadio vacío (ratio<15%): local gana 53.3% (sorprendentemente alto)
    #   Estadio medio (30-70%): local gana ~40%
    #   Estadio lleno (ratio>95%): local gana SÓLO 21.6%, visitante 45.9%
    # Inversión de la hipótesis clásica. Posibles causas:
    #   - Estadio vacío: partidos "triviales" donde el local es muy superior
    #   - Estadio lleno: partidos grandes, visitantes también son fuertes
    # Calibración conservadora, multiplicadores 0.02-0.04.
    att = features.get('attendance_ratio', {})
    if att.get('available'):
        ratio = att['ratio']
        att_str = f"{att['attendance']:,}/{att['capacity']:,} ({ratio*100:.0f}%)"

        # Estadio muy lleno (>95%) → favorece visitante/empate, NO local
        if ratio >= 0.95:
            away_win += 0.03 * (1 - away_win) * 0.5
            draw += 0.02 * (1 - draw) * 0.3
            home_win -= 0.04 * home_win
            adjustments.append({
                'type': 'sold_out',
                'direction': 'favor_away',
                'magnitude': 0.04,
                'reason': f"Estadio lleno ({att_str}). Backtest Liga MX: local gana solo 21.6% en llenos. Visitante 45.9%.",
            })
            confidence_penalty *= 0.95
        # Estadio vacío (<15%) → favorece local (sorpresa)
        elif ratio < 0.15:
            home_win += 0.03 * (1 - home_win) * 0.5
            away_win -= 0.02 * away_win
            adjustments.append({
                'type': 'very_low_attendance',
                'direction': 'favor_home',
                'magnitude': 0.03,
                'reason': f"Asistencia muy baja ({att_str}). Backtest: local gana 53% con estadio casi vacío.",
            })
        # Estadio muy vacío-medio (<30%) → pequeño empujón local
        elif ratio < 0.30:
            home_win += 0.015 * (1 - home_win) * 0.4
            adjustments.append({
                'type': 'low_attendance',
                'direction': 'favor_home',
                'magnitude': 0.015,
                'reason': f"Baja asistencia ({att_str}). Ligero empujón local por ambiente sin presión.",
            })
        # Estadio casi lleno (≥85%) → reduce home_win (favorece visitante)
        elif ratio >= 0.85:
            away_win += 0.015 * (1 - away_win) * 0.4
            adjustments.append({
                'type': 'high_attendance',
                'direction': 'favor_away',
                'magnitude': 0.015,
                'reason': f"Alta asistencia ({att_str}). Estadio lleno = partido difícil para local.",
            })

    # ── 5e. REFEREE BIAS (Fase 9) — sesgo arbitral histórico ──────────────────────
    ref = features.get('referee_bias', {})
    ref_bias = ref.get('bias_score', 0.0)
    ref_reliable = ref.get('is_reliable', False)
    ref_games = ref.get('games', 0)
    ref_name = ref.get('name', 'unknown')

    # Solo aplicar si tenemos stats confiables (>=30 partidos)
    if ref_reliable and abs(ref_bias) > 0.03:
        # Calibración: bias de ±0.10 → ±5pp en probabilidad final
        # Multiplicador 0.50 (aumentado de 0.30 en backtest Fase 9 inicial)
        # Bryson et al. paper sugiere efectos pequeños pero consistentes;
        # con Liga MX hemos observado diferencias >5pp en árbitros extremos.
        ref_adj_pp = ref_bias * 0.50  # ej: bias +0.10 → +5pp

        if ref_bias > 0:  #倾向于local
            home_win += ref_adj_pp / 100
            away_win -= ref_adj_pp / 100 * 0.6
            adjustments.append({
                'type': 'referee_home_bias',
                'direction': 'favor_home',
                'magnitude': round(ref_adj_pp, 3),
                'reason': f"Árbitro {ref_name} ({ref_games} partidos) tiene sesgo倾向于local: {100*ref_bias:+.1f}pp vs 50% neutral. HR={100*ref.get('home_win_rate', 0.5):.1f}%.",
            })
            confidence_penalty *= 0.96  # pequeño descuento por incertidumbre
        else:  #倾向于visitante
            away_win += -ref_adj_pp / 100  # ref_adj_pp es negativo, queremos sumar a away
            home_win -= -ref_adj_pp / 100 * 0.6
            adjustments.append({
                'type': 'referee_away_bias',
                'direction': 'favor_away',
                'magnitude': round(-ref_adj_pp, 3),
                'reason': f"Árbitro {ref_name} ({ref_games} partidos) tiene sesgo倾向于visitante: {100*ref_bias:+.1f}pp. HR={100*ref.get('home_win_rate', 0.5):.1f}%.",
            })
            confidence_penalty *= 0.96

    # ── 6. Presión DT (winless streak) — existente ──────────────────────────
    coach_h = features.get('coach_home', {})
    if coach_h.get('winless_streak', 0) >= 5:
        adjustments.append({
            'type': 'home_dt_pressure',
            'direction': 'reduce_home_win',
            'magnitude': 0.10,
            'reason': f"DT local sin ganar en {coach_h['winless_streak']} partidos. Presión institucional alta."
        })
        home_win -= 0.10 * home_win
        confidence_penalty *= 0.88

    coach_a = features.get('coach_away', {})
    if coach_a.get('winless_streak', 0) >= 5:
        adjustments.append({
            'type': 'away_dt_pressure',
            'direction': 'reduce_away_win',
            'magnitude': 0.10,
            'reason': f"DT visitante sin ganar en {coach_a['winless_streak']} partidos."
        })
        away_win -= 0.10 * away_win
        confidence_penalty *= 0.88

    # ── 7. DERBY DETECTION ──────────────────────────────────────────────────
    home_team_name = features.get('home_team_name', '')
    away_team_name = features.get('away_team_name', '')
    derby = detect_derby(home_team_name, away_team_name)

    if derby:
        flatten = 0.15
        avg = (home_win + draw + away_win) / 3
        home_win = home_win * (1 - flatten) + avg * flatten
        away_win = away_win * (1 - flatten) + avg * flatten
        draw = draw * (1 - flatten) + avg * flatten

        adjustments.append({
            'type': 'derby',
            'direction': 'flatten_all',
            'magnitude': flatten,
            'reason': f"{derby['name']} — {derby['description']}"
        })
        confidence_penalty *= 0.80

    # ── 8. NARRATIVES DEL USUARIO ──────────────────────────────────────────
    team_narratives = narratives.get('narratives', [])
    for narr in team_narratives:
        if not narr.get('active', False):
            continue
        team = narr.get('team', '').lower()
        weight = narr.get('weight', 0.5)
        description = narr.get('description', '')

        if team in home_team_name.lower() or team in away_team_name.lower():
            direction = narr.get('direction', 'unknown')
            magnitude = (weight - 0.5) * 0.12

            if 'favor_home' in direction:
                home_win += magnitude * (1 - home_win) * 0.5
            elif 'favor_away' in direction:
                away_win += magnitude * (1 - away_win) * 0.5
            else:
                draw += magnitude * 0.3

            adjustments.append({
                'type': 'user_narrative',
                'direction': direction,
                'magnitude': round(magnitude, 4),
                'reason': f"[Ángel]: {description}"
            })
            confidence_penalty *= (1.0 - weight * 0.05)

    # ── 9. Normalizar ──────────────────────────────────────────────────────
    total = home_win + draw + away_win
    if total > 0:
        home_win /= total; draw /= total; away_win /= total

    # ── 10. Confidence final ──────────────────────────────────────────────
    confidence = model_output['model_confidence'] * confidence_penalty

    # ── 11. Contrarian view ────────────────────────────────────────────────
    contrarian = _generate_contrarian_view_v2(features, model_output, adjustments)

    return {
        'home_win': round(home_win, 4),
        'draw': round(draw, 4),
        'away_win': round(away_win, 4),
        'confidence': round(min(0.92, confidence), 3),
        'heuristic_adjustments': adjustments,
        'contrarian_view': contrarian,
        'is_derby': derby is not None,
        'derby_info': derby,
    }


def _generate_contrarian_view_v2(features, model_output, adjustments):
    """Vista contrarian mejorada con los nuevos features."""
    views = []

    home_form = features.get('home_form', {})
    away_form = features.get('away_form', {})

    if home_form.get('wins', 0) >= 3:
        recent = home_form.get('form_str', '')
        if 'W' in recent[-2:]:
            views.append(
                "Cuidado: la forma reciente del local puede incluir suerte "
                "(penales, goles en el 90+). Verificar si los xG reales respaldan la racha."
            )

    # Altitud
    alt = features.get('altitude', {})
    if alt.get('home_altitude', 0) >= 2400:
        views.append(
            "La altitud ayuda, pero equipos como Tigres y Rayados están "
            "acostumbrados a viajar. El efecto suele reducirse en partidos de noche."
        )

    # Nuevo: coach new bounce
    home_coach_t = features.get('home_coach_tenure', {})
    if home_coach_t.get('is_new_coach', False):
        views.append(
            f"⚠️ DT local solo lleva {home_coach_t.get('tenure_days', 0)} días. "
            "El 'new manager bounce' puede ser temporal — verificar si el sistema táctico está implementado."
        )

    # Nuevo: travel fatigue
    away_travel = features.get('away_travel', {})
    if away_travel.get('distance_7d_km', 0) > 2500:
        views.append(
            f"⚠️ Visitante ha viajado {away_travel['distance_7d_km']:.0f}km en 7 días. "
            "Fatiga visible en segunda parte y en pressing."
        )

    # H2H ruido
    h2h = features.get('h2h', {})
    if h2h.get('total', 0) < 6:
        views.append(
            f"Solo {h2h.get('total', 0)} partidos de H2H. "
            "Muestra pequeño para extraer conclusiones firmes."
        )

    # Narrative bias
    if any(a['type'] == 'user_narrative' for a in adjustments):
        views.append(
            "Narrativa de Ángel detectada. "
            "Si es inteligencia de scouting real (no solo intuición), es valiosa. "
            "Si es sesgo de confirmación, puede perjudicar."
        )

    return " | ".join(views) if views else "Sin ángulos contrarios detectados."



def _generate_contrarian_view(
    features: Dict[str, Any],
    model_output: Dict[str, Any],
    adjustments: List[Dict]
) -> str:
    """
    Genera una vista contrarian: ¿qué argumentaría un analista
   反对 la predicción del modelo?
    """
    views = []

    home_form = features.get('home_form', {})
    away_form = features.get('away_form', {})

    # "El equipo 'en forma' puede estar sobreestimado"
    if home_form.get('wins', 0) >= 3:
        recent = home_form.get('form_str', '')
        if 'W' in recent[-2:]:
            views.append(
                "Cuidado: la forma reciente del local puede incluir suerte "
                "(penales, goles en el 90+). Verificar si los xG reales respaldan la racha."
            )

    # "La altitud pesa pero..."
    alt = features.get('altitude', {})
    if alt.get('home_altitude', 0) >= 2400:
        views.append(
            "La altitud ayuda, pero equipos como Tigres y Rayados están "
            "acostumbrados a viajar. El efecto suele reducirse en partidos de noche."
        )

    # "El H2H puede ser ruido"
    h2h = features.get('h2h', {})
    if h2h.get('total', 0) < 6:
        views.append(
            f"Solo {h2h.get('total', 0)} partidos de H2H. "
            "样本 pequeño para extraer conclusiones firmes."
        )

    # "El modelo no ve esto..."
    if any(a['type'] == 'user_narrative' for a in adjustments):
        views.append(
            "Narrativa de Ángel detectada. "
            "Si es inteligencia de scouting real (no solo intuición), es valiosa. "
            "Si es sesgo de confirmación, puede perjudicar."
        )

    return " | ".join(views) if views else "Sin ángulos contrarios detectados."


# ─────────────────────────────────────────────────────────────────────────────
# FINAL PROBABILITIES → BETTING ODDS CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

def prob_to_odds(prob: float) -> float:
    """Convierte probabilidad implícita a cuota decimal."""
    if prob <= 0:
        return 99.99
    return round(1.0 / prob, 2)


def find_value_bets(
    adj_probs: Dict[str, float],
    market_odds: Optional[Dict[str, float]] = None,
    min_edge: float = 0.05
) -> List[Dict[str, Any]]:
    """
    Identifica apuestas de valor.

    Si market_odds está disponible, compara.
    Si no, usa la "base rate" del modelo como referencia.

    Returns: lista de {
        'selection': 'home/draw/away',
        'probability': float,
        'odds': float,
        'market_odds': float,
        'edge': float,
        'value': bool,
    }
    """
    selections = {
        'home': adj_probs['home_win'],
        'draw': adj_probs['draw'],
        'away': adj_probs['away_win'],
    }

    if market_odds:
        results = []
        for sel, prob in selections.items():
            mkt_odds = market_odds.get(sel, prob_to_odds(prob))
            fair_odds = prob_to_odds(prob)
            edge = (fair_odds / mkt_odds) - 1 if mkt_odds > 0 else 0

            results.append({
                'selection': sel,
                'probability': round(prob, 4),
                'fair_odds': fair_odds,
                'market_odds': mkt_odds,
                'edge_pct': round(edge * 100, 2),
                'has_value': edge >= min_edge,
            })
        return results
    else:
        # Sin mercado → mostrar solo probabilidades y cuotas justas
        return [
            {
                'selection': sel,
                'probability': round(prob, 4),
                'fair_odds': prob_to_odds(prob),
                'market_odds': None,
                'edge_pct': 0,
                'has_value': False,
                'note': 'Sin cuotas de mercado — usa probabilidad del modelo'
            }
            for sel, prob in selections.items()
        ]
