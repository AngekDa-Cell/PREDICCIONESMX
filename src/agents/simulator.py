"""
simulator.py — Simulador de agentes Bull/Bear/Numérico para backtest.

En el backtest piloto NO queremos gastar 340 × 3 = 1020 calls LLM.
Este módulo genera "reports sintéticos" de Bull/Bear basados en
heurísticas sobre los datos del partido, y reutiliza el ensemble
numérico real como agente Numérico.

Objetivo: validar el ALGORITMO del juez (DWC-MAD) y la mecánica del
orquestador antes de invertir en sub-agents LLM reales.

El simulador:
- Numérico: ejecuta el ensemble real (predictions_mx actual)
- Bull: sesgo pro-home proporcional a localía + forma reciente
- Bear: sesgo pro-away proporcional a forma reciente del visitante + ventajas

NO pretende ser perfecto. Solo lo suficiente para validar la mecánica.
"""

import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

# Setup paths
_AGENT_DIR = Path(__file__).resolve().parent
_PROYECTOS_ROOT = _AGENT_DIR.parent.parent.parent  # /workspace
if str(_PROYECTOS_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROYECTOS_ROOT))

# Reutilizamos el ensemble numérico real



def get_match_context(conn: sqlite3.Connection, fixture_id: int) -> Dict[str, Any]:
    """
    Extrae contexto del partido: equipos, fecha, venue, scores.
    
    Returns dict con: home_team, away_team, date, venue, etc.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            f.id, f.starting_at, f.season_id,
            ht.id, ht.name, ht.short_code,
            at.id, at.name, at.short_code,
            v.name as venue_name, v.city, v.capacity, v.altitude_m,
            f.home_score, f.away_score
        FROM fixtures f
        JOIN teams ht ON ht.id = f.home_team_id
        JOIN teams at ON at.id = f.away_team_id
        LEFT JOIN venues v ON v.id = f.venue_id
        WHERE f.id = ?
    """, (fixture_id,))
    row = cur.fetchone()
    if not row:
        return {}
    
    return {
        "fixture_id": row[0],
        "date": row[1],
        "season_id": row[2],
        "home_team_id": row[3],
        "home_team": row[4],
        "home_team_short": row[5],
        "away_team_id": row[6],
        "away_team": row[7],
        "away_team_short": row[8],
        "venue_name": row[9],
        "venue_city": row[10],
        "venue_capacity": row[11],
        "venue_altitude_m": row[12],
        "home_score": row[13],
        "away_score": row[14],
        "result": (
            "home_win" if (row[13] is not None and row[14] is not None and row[13] > row[14])
            else "away_win" if (row[13] is not None and row[14] is not None and row[13] < row[14])
            else "draw" if (row[13] is not None and row[14] is not None)
            else None
        ),
    }


def simulate_bull_local(context: Dict[str, Any], ensemble_probs: Dict[str, float]) -> Dict[str, Any]:
    """
    Simula agente Bull-Local.
    
    Genera argumentos a favor del local basados en heurísticas:
    - Localía siempre suma ~0.05-0.10 al win_prob del local
    - Si ensemble ya favorece al local → Bull refuerza (+0.05)
    - Si ensemble no favorece → Bull discrepa ligeramente (-0.05)
    
    Args:
        context: dict con datos del partido (de get_match_context)
        ensemble_probs: dict con probs del ensemble numérico
    
    Returns:
        JSON-serializable dict simulando output de Bull.
    """
    home_win_ensemble = ensemble_probs.get("home_win", 0.33)
    
    # Sesgo pro-home: +0.08 a home_win, restar proporcionalmente
    bull_home_win = min(0.85, home_win_ensemble + 0.08)
    
    # Si ensemble favorece muy poco al local (<0.4), Bull es más conservador
    if home_win_ensemble < 0.40:
        bull_home_win = min(bull_home_win, home_win_ensemble + 0.05)
    
    # Argumentos sintéticos
    arguments = [
        f"Localía en {context.get('venue_name', 'estadio local')}: ventaja tradicional",
        f"Ensemble da {home_win_ensemble:.1%} al local — base cuantitativa",
    ]
    
    if context.get("venue_altitude_m") and context["venue_altitude_m"] > 1500:
        arguments.append(f"Altitud {context['venue_altitude_m']}m favorece al local aclimatado")
    
    if context.get("venue_capacity"):
        arguments.append(f"Estadio con capacidad {context['venue_capacity']:,}")
    
    # Riesgo estándar
    risks = [
        f"Visitante ({context.get('away_team', 'rival')}) puede aprovechar contraataque",
    ]
    
    return {
        "agent": "bull_local",
        "match_id": str(context.get("fixture_id", "")),
        "team_favored": context.get("home_team"),
        "win_probability_estimate": round(bull_home_win, 4),
        "ensemble_prob_home": round(home_win_ensemble, 4),
        "delta_vs_ensemble": round(bull_home_win - home_win_ensemble, 4),
        "key_arguments": arguments[:5],
        "risks_acknowledged": risks[:2],
        "confidence": 0.55,
        "reasoning_summary": f"Local {context.get('home_team_short', '?')} tiene ventaja de localía. Ensemble da {home_win_ensemble:.1%}. Bull refuerza a {bull_home_win:.1%} por argumentos cualitativos.",
    }


def simulate_bear_visitante(context: Dict[str, Any], ensemble_probs: Dict[str, float]) -> Dict[str, Any]:
    """
    Simula agente Bear-Visitante.
    
    Sesgo pro-away: +0.08 a away_win.
    """
    away_win_ensemble = ensemble_probs.get("away_win", 0.33)
    
    bear_away_win = min(0.85, away_win_ensemble + 0.08)
    
    if away_win_ensemble < 0.30:
        bear_away_win = min(bear_away_win, away_win_ensemble + 0.05)
    
    arguments = [
        f"Visitante ({context.get('away_team', '?')}) puede capitalizar errores locales",
        f"Ensemble da {away_win_ensemble:.1%} al visitante — base cuantitativa",
        f"Local {context.get('home_team_short', '?')} viene con presión de resultado",
    ]
    
    if context.get("venue_altitude_m") and context["venue_altitude_m"] > 1800:
        arguments.append(f"Visitantes aclimatados a altitud alta = ventaja")
    
    risks = [
        f"Local {context.get('home_team_short', '?')} tiene mejor récord en casa",
    ]
    
    return {
        "agent": "bear_visitante",
        "match_id": str(context.get("fixture_id", "")),
        "team_favored": context.get("away_team"),
        "win_probability_estimate": round(bear_away_win, 4),
        "ensemble_prob_away": round(away_win_ensemble, 4),
        "delta_vs_ensemble": round(bear_away_win - away_win_ensemble, 4),
        "key_arguments": arguments[:5],
        "risks_acknowledged": risks[:2],
        "confidence": 0.55,
        "reasoning_summary": f"Visitante {context.get('away_team_short', '?')} tiene oportunidad. Ensemble da {away_win_ensemble:.1%}. Bear refuerza a {bear_away_win:.1%}.",
    }


def run_numerico_real(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ejecuta el ensemble numérico REAL (predictions_mx actual).
    
    Returns dict compatible con AgentReport.
    """
    try:
        fixture_id = context.get("fixture_id")
        season_id = context.get("season_id")
        if not fixture_id or not season_id:
            return _numerico_fallback(context, error="missing_ids")
        
        # Conexión al ensemble real
        from predict.cli import generate_prediction, get_conn
        conn = get_conn()
        
        try:
            result = generate_prediction(
                conn=conn,
                home_team_id=context["home_team_id"],
                away_team_id=context["away_team_id"],
                season_id=season_id,
                fixture_id=int(fixture_id),
                fixture_date=context.get("date"),
                log_to_db=False,  # backtest: no contaminar bitácora
                recalibrate=False,
                use_shrinkage=True,
            )
        finally:
            conn.close()
        
        if "error" in result:
            return _numerico_fallback(context, error=result["error"])
        
        # Schema real de generate_prediction: report['probabilities']['1'/'X'/'2']['prob']
        probs_section = result.get("probabilities", {})
        home_win = float(probs_section.get("1", {}).get("prob", 0.33))
        draw = float(probs_section.get("X", {}).get("prob", 0.34))
        away_win = float(probs_section.get("2", {}).get("prob", 0.33))
        
        meta = result.get("meta", {})
        confidence = float(meta.get("model_confidence", 0.5))
        
        return {
            "agent": "numerico",
            "match_id": str(fixture_id),
            "probs": {
                "home_win": home_win,
                "draw": draw,
                "away_win": away_win,
            },
            "predicted_outcome": meta.get("predicted_outcome", "home_win"),
            "confidence": confidence,
            "components": {
                "xg": meta.get("xg_home_prob"),
                "elo_diff": meta.get("elo_diff"),
                "shrinkage": meta.get("shrinkage_factor"),
            },
            "reasoning_summary": f"Ensemble xG+Elo+DC+heur: {home_win:.1%} home, {draw:.1%} draw, {away_win:.1%} away (conf={confidence:.2f})",
        }
    except Exception as e:
        return _numerico_fallback(context, error=str(e))


def _numerico_fallback(context: Dict[str, Any], error: Optional[str] = None) -> Dict[str, Any]:
    """Fallback si predict_match falla."""
    return {
        "agent": "numerico",
        "match_id": str(context.get("fixture_id", "")),
        "probs": {"home_win": 0.45, "draw": 0.27, "away_win": 0.28},
        "predicted_outcome": "home_win",
        "confidence": 0.50,
        "reasoning_summary": f"Fallback (ensemble error: {error or 'unknown'})",
    }


def simulate_full_debate(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simula el debate completo para un partido: Numérico + Bull + Bear + Juez.
    
    Returns dict con todos los reports y la decisión final del juez.
    """
    # 1. Numérico real
    numerico_report = run_numerico_real(context)
    ensemble_probs = numerico_report["probs"]
    
    # 2. Bull y Bear simulados (basados en ensemble + sesgo)
    bull_report = simulate_bull_local(context, ensemble_probs)
    bear_report = simulate_bear_visitante(context, ensemble_probs)
    
    # 3. Juez
    try:
        from .judge import judge_from_dicts
    except ImportError:
        from proyectos.src.agents.judge import judge_from_dicts  # type: ignore
    judge_output = judge_from_dicts(
        {
            "bull_local": bull_report,
            "bear_visitante": bear_report,
            "numerico": numerico_report,
        },
        match_id=str(context.get("fixture_id", "")),
    )
    
    return {
        "fixture_id": context.get("fixture_id"),
        "match_id": str(context.get("fixture_id", "")),
        "context": {
            "home_team": context.get("home_team"),
            "away_team": context.get("away_team"),
            "date": context.get("date"),
            "venue": context.get("venue_name"),
            "result": context.get("result"),  # home_win/draw/away_win si ya se jugó
        },
        "agents": {
            "numerico": numerico_report,
            "bull_local": bull_report,
            "bear_visitante": bear_report,
        },
        "judge": judge_output,
    }
