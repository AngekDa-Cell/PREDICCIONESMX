"""
feature_block.py — Extrae features específicas del partido para inyectar a Bull/Bear.

Los sub-agentes LLM (Bull/Bear) reciben un bloque de features CONCRETAS del partido,
no solo metadatos básicos. Esto les permite argumentar con datos, no con opiniones.

Features inyectadas (las 8 más relevantes para debate cualitativo):
1. Forma reciente (W-D-L últimos 5) — momentum básico
2. Momentum compuesto (forma ponderada exponencialmente)
3. H2H últimos 10 enfrentamientos
4. xG rolling (proxy de calidad de chances)
5. Attendance ratio (estadio lleno/vacío)
6. Referee bias (si hay datos del árbitro)
7. Weather (heat/wet si está disponible)
8. Rest days / fixture congestion
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Setup paths
_AGENT_DIR = Path(__file__).resolve().parent
_PROYECTOS_ROOT = _AGENT_DIR.parent.parent.parent
if str(_PROYECTOS_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROYECTOS_ROOT))

import sqlite3

try:
    from proyectos.src.predict.features import (
        get_team_form, get_head_to_head, get_composite_momentum,
        get_attendance_ratio, get_referee_bias, get_match_weather,
        rest_days_advantage, get_fixture_congestion,
    )
except ImportError:
    from predict.features import (
        get_team_form, get_head_to_head, get_composite_momentum,
        get_attendance_ratio, get_referee_bias, get_match_weather,
        rest_days_advantage, get_fixture_congestion,
    )


def build_feature_block(
    conn: sqlite3.Connection,
    context: Dict[str, Any],
) -> str:
    """
    Construye un bloque de features formateado para inyectar a prompts Bull/Bear.
    
    Args:
        conn: conexión a BD
        context: dict del partido (de get_match_context)
    
    Returns:
        String formateado con las 8 features principales
    """
    fixture_id = context.get("fixture_id")
    home_id = context.get("home_team_id")
    away_id = context.get("away_team_id")
    fixture_date = context.get("date")
    
    if not all([fixture_id, home_id, away_id, fixture_date]):
        return "⚠️ Features no disponibles (datos incompletos)"
    
    # Convertir fecha a string si es datetime
    if hasattr(fixture_date, "isoformat"):
        fixture_date_str = fixture_date.isoformat()
    else:
        fixture_date_str = str(fixture_date)
    
    lines = []
    
    # 1. Forma reciente
    try:
        home_form = get_team_form(conn, home_id, before_date=fixture_date_str, n=5)
        away_form = get_team_form(conn, away_id, before_date=fixture_date_str, n=5)
        lines.append("## Forma reciente (últimos 5 partidos)")
        lines.append(f"- Local: {home_form.get('form_str', 'N/A')} "
                    f"({home_form.get('wins', 0)}W-{home_form.get('draws', 0)}D-"
                    f"{home_form.get('losses', 0)}L, {home_form.get('goals_for', 0)}GF-"
                    f"{home_form.get('goals_against', 0)}GA, momentum={home_form.get('momentum', 0):.2f})")
        lines.append(f"- Visitante: {away_form.get('form_str', 'N/A')} "
                    f"({away_form.get('wins', 0)}W-{away_form.get('draws', 0)}D-"
                    f"{away_form.get('losses', 0)}L, {away_form.get('goals_for', 0)}GF-"
                    f"{away_form.get('goals_against', 0)}GA, momentum={away_form.get('momentum', 0):.2f})")
    except Exception as e:
        logger.warning("feature_block.forma_reciente error: %s", e)
        lines.append("## Forma reciente: ⚠️ sin datos")
    
    # 2. Momentum compuesto
    try:
        home_mom = get_composite_momentum(conn, home_id, before_date=fixture_date_str)
        away_mom = get_composite_momentum(conn, away_id, before_date=fixture_date_str)
        lines.append("")
        lines.append("## Momentum compuesto (ponderado)")
        lines.append(f"- Local: {home_mom.get('composite_score', 0):.2f} "
                    f"(trend={home_mom.get('trend', 0):.2f}, consistency={home_mom.get('consistency', 0):.2f})")
        lines.append(f"- Visitante: {away_mom.get('composite_score', 0):.2f} "
                    f"(trend={away_mom.get('trend', 0):.2f}, consistency={away_mom.get('consistency', 0):.2f})")
    except Exception as e:
        logger.warning("feature_block.momentum_compuesto error: %s", e)
        lines.append("## Momentum: ⚠️ sin datos")
    
    # 3. H2H últimos 10
    try:
        h2h = get_head_to_head(conn, home_id, away_id, limit=10)
        if h2h and h2h.get("matches", 0) > 0:
            lines.append("")
            lines.append(f"## H2H últimos {h2h.get('matches', 0)} partidos")
            lines.append(f"- Local wins: {h2h.get('home_wins', 0)}, "
                        f"Draws: {h2h.get('draws', 0)}, "
                        f"Visitante wins: {h2h.get('away_wins', 0)}")
            lines.append(f"- Local win rate: {h2h.get('h_win_rate', 0):.1%}")
            lines.append(f"- Visitante win rate: {h2h.get('a_win_rate', 0):.1%}")
        else:
            lines.append("")
            lines.append("## H2H: Sin datos suficientes")
    except Exception as e:
        logger.warning("feature_block.h2h error: %s", e)
        lines.append("## H2H: ⚠️ sin datos")
    
    # 4. xG rolling recent — placeholder honesto
    lines.append("")
    lines.append("## xG rolling: ver data/xg_model.json (Fase 8)")
    lines.append("  (xG se integra en el ensemble numérico; no se inyecta raw a Bull/Bear para evitar conflicto de escalas)")
    
    # 5. Attendance ratio
    try:
        att = get_attendance_ratio(conn, fixture_id)
        if att and att.get("ratio") is not None:
            lines.append("")
            lines.append(f"## Attendance: {att.get('ratio', 0):.1%} de capacidad")
            if att.get("ratio", 0) >= 0.90:
                lines.append("  → Estadio CASI LLENO (ambiente intenso)")
            elif att.get("ratio", 0) >= 0.70:
                lines.append("  → Estadio bien lleno")
            elif att.get("ratio", 0) <= 0.50:
                lines.append("  → Estadio con muchos huecos")
            else:
                lines.append("  → Estadio moderadamente lleno")
        else:
            lines.append("")
            lines.append("## Attendance: ⚠️ sin datos")
    except Exception as e:
        logger.warning("feature_block.attendance error: %s", e)
        lines.append("## Attendance: ⚠️ sin datos")
    
    # 6. Referee bias
    try:
        ref = get_referee_bias(conn, fixture_id)
        if ref and ref.get("referee_name"):
            lines.append("")
            lines.append(f"## Árbitro: {ref.get('referee_name')}")
            lines.append(f"- Bias score: {ref.get('bias_score', 0):+.3f} "
                        f"(negativo=favorece visitante, positivo=favorece local)")
            lines.append(f"- Partidos dirigidos: {ref.get('matches_officiated', 0)}")
            if ref.get("matches_officiated", 0) >= 30:
                lines.append(f"- Estadio lleno de {ref.get('ratio', 0):.1%}: visitante tiene ventaja (Fase 9 hallazgo)")
        else:
            lines.append("")
            lines.append("## Árbitro: ⚠️ sin datos")
    except Exception as e:
        logger.warning("feature_block.referee error: %s", e)
        lines.append("## Árbitro: ⚠️ sin datos")
    
    # 7. Weather
    try:
        weather = get_match_weather(conn, fixture_id)
        if weather and weather.get("temperature_max") is not None:
            lines.append("")
            lines.append(f"## Clima: {weather.get('temperature_max', 0):.1f}°C max, "
                        f"{weather.get('precipitation', 0):.1f}mm lluvia, "
                        f"humedad {weather.get('humidity_mean', 0):.0f}%")
            if weather.get("temperature_max", 0) >= 32:
                lines.append("  → Calor extremo (fatiga para visitante no aclimatado)")
            elif weather.get("precipitation", 0) >= 5:
                lines.append("  → Lluvia significativa (puede afectar juego)")
        else:
            lines.append("")
            lines.append("## Clima: ⚠️ sin datos")
    except Exception as e:
        logger.warning("feature_block.weather error: %s", e)
        lines.append("## Clima: ⚠️ sin datos")
    
    # 8. Rest days
    try:
        rest = rest_days_advantage(conn, home_id, away_id, fixture_date_str)
        lines.append("")
        lines.append(f"## Descanso: Local {rest.get('home_rest', 0)}d, "
                    f"Visitante {rest.get('away_rest', 0)}d "
                    f"(Δ={rest.get('rest_diff', 0):+d} días)")
        
        cong_h = get_fixture_congestion(conn, home_id, fixture_date_str)
        cong_a = get_fixture_congestion(conn, away_id, fixture_date_str)
        if cong_h.get("congested") or cong_a.get("congested"):
            congested_team = "Local" if cong_h.get("congested") else "Visitante"
            lines.append(f"  → {congested_team} viene de fixture congestionada "
                        f"({cong_h.get('matches_last_7d', 0) if cong_h.get('congested') else cong_a.get('matches_last_7d', 0)} partidos en 7 días)")
    except Exception as e:
        logger.warning("feature_block.rest_days error: %s", e)
        lines.append("## Descanso: ⚠️ sin datos")
    
    return "\n".join(lines)