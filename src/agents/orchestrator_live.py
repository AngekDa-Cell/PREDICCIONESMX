"""
orchestrator_live.py — Debate multi-agente con sub-agentes LLM REALES (Fase 10.2).

Usa `sessions_spawn` para lanzar Bull y Bear en paralelo como sub-agentes
verdaderos con sus prompts y permisos restringidos.

⚠️ Solo funciona dentro del runtime OpenClaw (sesión main con acceso a sessions_spawn).
Para backtest/validación usar `orchestrator.simulate_*()`.

Flujo:
1. Calcula contexto + ensemble numérico (local, rápido)
2. Construye prompts para Bull y Bear
3. Lanza 2 sub-agentes en PARALELO vía sessions_spawn
4. sessions_yield → espera completion events
5. Parsea JSON outputs de cada sub-agente
6. Ejecuta juez DWC-MAD
7. Retorna debate completo con metadata de latencia
"""

import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# Setup paths (mismo patrón que orchestrator.py)
_AGENT_DIR = Path(__file__).resolve().parent
_PROYECTOS_ROOT = _AGENT_DIR.parent.parent.parent
if str(_PROYECTOS_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROYECTOS_ROOT))

from proyectos.src.agents.orchestrator import (
    get_match_context, save_report, DATA_DIR, DB_PATH, REPORTS_DIR,
)
from proyectos.src.agents.prompts import (
    BULL_LOCAL_PROMPT, BEAR_VISITANTE_PROMPT, JUEZ_PROMPT,
)
from proyectos.src.agents.permissions import get_tools_for_role
from proyectos.src.agents.judge import judge_from_dicts
from proyectos.src.agents.simulator import run_numerico_real


# ─────────────────────────────────────────────────────────────────────────────
# PARSING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extrae el primer JSON válido de un texto.
    
    Busca bloques ```json ... ``` primero, luego busca JSON inline.
    Retorna None si no encuentra JSON válido.
    """
    if not text:
        return None
    
    # 1. Buscar bloque ```json ... ```
    json_block = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass
    
    # 2. Buscar cualquier {...} parseable
    candidates = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    
    return None


def parse_agent_output(
    session_messages: List[Dict[str, Any]],
    expected_agent: str,
) -> Dict[str, Any]:
    """
    Parsea el output de un sub-agente desde sus mensajes.
    
    Busca el ÚLTIMO mensaje del agente que contenga JSON parseable.
    Si no encuentra, retorna un fallback heurístico.
    """
    # Iterar de más reciente a más antiguo
    for msg in reversed(session_messages):
        role = msg.get("role", "")
        if role not in ("assistant", "agent"):
            continue
        
        content = msg.get("content", "")
        if isinstance(content, list):
            # Algunos formatos tienen content como lista de bloques
            content = " ".join(
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in content
            )
        
        parsed = extract_json_from_text(str(content))
        if parsed:
            # Validar que sea del agente esperado
            if parsed.get("agent") == expected_agent:
                return parsed
            # Si no coincide el agent field pero hay JSON válido, agregarlo
            parsed.setdefault("agent", expected_agent)
            return parsed
    
    # Fallback si no se pudo parsear
    return {
        "agent": expected_agent,
        "error": "no_json_found",
        "fallback_used": True,
        "team_favored": "unknown",
        "win_probability_estimate": 0.50,
        "confidence": 0.30,
        "reasoning_summary": "Fallback: sub-agente no devolvió JSON parseable",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def build_bull_task(
    context: Dict[str, Any],
    ensemble_probs: Dict[str, float],
    fixture_id: int,
    feature_block: Optional[str] = None,
) -> str:
    """Construye el task completo para Bull-Local."""
    ctx_str = _format_context(context)
    probs_str = _format_probs(ensemble_probs)
    if feature_block is None:
        feature_block = "(Features no inyectadas — versión legacy)"
    return BULL_LOCAL_PROMPT.format(
        fixture_context=ctx_str,
        feature_block=feature_block,
        ensemble_probs=probs_str,
        match_id=str(fixture_id),
    )


def build_bear_task(
    context: Dict[str, Any],
    ensemble_probs: Dict[str, float],
    fixture_id: int,
    feature_block: Optional[str] = None,
) -> str:
    """Construye el task completo para Bear-Visitante."""
    ctx_str = _format_context(context)
    probs_str = _format_probs(ensemble_probs)
    if feature_block is None:
        feature_block = "(Features no inyectadas — versión legacy)"
    return BEAR_VISITANTE_PROMPT.format(
        fixture_context=ctx_str,
        feature_block=feature_block,
        ensemble_probs=probs_str,
        match_id=str(fixture_id),
    )


def _format_context(context: Dict[str, Any]) -> str:
    """Formatea el contexto del partido para inyectar al prompt."""
    lines = [
        f"- Fixture ID: {context.get('fixture_id')}",
        f"- Fecha: {context.get('date')}",
        f"- Local: {context.get('home_team')} ({context.get('home_team_short')})",
        f"- Visitante: {context.get('away_team')} ({context.get('away_team_short')})",
    ]
    if context.get("venue_name"):
        lines.append(f"- Venue: {context.get('venue_name')} ({context.get('venue_city')})")
    if context.get("venue_capacity"):
        lines.append(f"- Capacidad: {context.get('venue_capacity'):,}")
    if context.get("venue_altitude_m"):
        lines.append(f"- Altitud: {context.get('venue_altitude_m')}m")
    return "\n".join(lines)


def _format_probs(probs: Dict[str, float]) -> str:
    """Formatea probs del ensemble para inyectar al prompt."""
    return (
        f"- home_win: {probs.get('home_win', 0.33):.1%}\n"
        f"- draw: {probs.get('draw', 0.34):.1%}\n"
        f"- away_win: {probs.get('away_win', 0.33):.1%}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODO LIVE — Orquestador real con sessions_spawn
# ─────────────────────────────────────────────────────────────────────────────

def orchestrate_live(
    conn: sqlite3.Connection,
    fixture_id: int,
    timeout_seconds: int = 240,
) -> Dict[str, Any]:
    """
    Debate completo con sub-agentes LLM REALES vía sessions_spawn.
    
    Args:
        conn: conexión a predictions_mx.db
        fixture_id: ID del partido
        timeout_seconds: timeout por sub-agente
    
    Returns:
        Dict con debate completo + metadata de latencia
    """
    start_ts = datetime.now()
    
    # 1. Contexto + ensemble numérico (local)
    context = get_match_context(conn, fixture_id)
    if not context:
        return {"error": f"fixture {fixture_id} not found", "fixture_id": fixture_id}
    
    numerico_report = run_numerico_real(context)
    ensemble_probs = numerico_report["probs"]
    
    # 2. Extraer features específicas del partido (Fase 10.2 fix)
    from proyectos.src.agents.feature_block import build_feature_block
    feature_block = build_feature_block(conn, context)
    
    # 3. Construir prompts CON features inyectadas
    bull_task = build_bull_task(context, ensemble_probs, fixture_id, feature_block)
    bear_task = build_bear_task(context, ensemble_probs, fixture_id, feature_block)
    
    # 3. Lanzar sub-agentes en paralelo
    # IMPORTANTE: estos imports solo funcionan dentro del runtime OpenClaw
    try:
        from sessions_spawn import spawn  # type: ignore
        from sessions_yield import yield_session  # type: ignore
    except ImportError:
        return {
            "error": "not_in_openclaw_runtime",
            "message": (
                "orchestrate_live() requiere runtime OpenClaw (sessions_spawn). "
                "Para backtest usar simulate."
            ),
            "fixture_id": fixture_id,
        }
    
    # Lanzar ambos en paralelo
    bull_session_id = spawn(
        task=bull_task,
        task_name=f"bull_local_{fixture_id}",
        tools_allow=get_tools_for_role("bull_local"),
        timeout_seconds=timeout_seconds,
    )
    bear_session_id = spawn(
        task=bear_task,
        task_name=f"bear_visitante_{fixture_id}",
        tools_allow=get_tools_for_role("bear_visitante"),
        timeout_seconds=timeout_seconds,
    )
    
    # 4. Esperar a ambos
    completed = yield_session([bull_session_id, bear_session_id])
    
    # 5. Extraer outputs
    bull_messages = completed.get(bull_session_id, [])
    bear_messages = completed.get(bear_session_id, [])
    
    bull_report = parse_agent_output(bull_messages, "bull_local")
    bear_report = parse_agent_output(bear_messages, "bear_visitante")
    
    # 6. Juez DWC-MAD
    judge_output = judge_from_dicts(
        {
            "bull_local": bull_report,
            "bear_visitante": bear_report,
            "numerico": numerico_report,
        },
        match_id=str(fixture_id),
    )
    
    # 7. Metadata
    elapsed = (datetime.now() - start_ts).total_seconds()
    
    debate = {
        "fixture_id": fixture_id,
        "match_id": str(fixture_id),
        "context": {
            "home_team": context.get("home_team"),
            "away_team": context.get("away_team"),
            "date": context.get("date"),
            "venue": context.get("venue_name"),
            "result": context.get("result"),
        },
        "agents": {
            "numerico": numerico_report,
            "bull_local": bull_report,
            "bear_visitante": bear_report,
        },
        "judge": judge_output,
        "mode": "live",
        "timestamp": datetime.now().isoformat(),
        "latency_sec": elapsed,
        "session_ids": {
            "bull_local": bull_session_id,
            "bear_visitante": bear_session_id,
        },
    }
    
    save_report(debate, fixture_id)
    return debate


# ─────────────────────────────────────────────────────────────────────────────
# MODO MOCK — Para testing sin runtime OpenClaw
# ─────────────────────────────────────────────────────────────────────────────

def orchestrate_live_mock(
    conn: sqlite3.Connection,
    fixture_id: int,
    bull_output: Dict[str, Any],
    bear_output: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Versión mock de orchestrate_live para tests.
    
    Recibe outputs ya parseados (en lugar de spawnear sub-agentes).
    Útil para:
    - Tests unitarios (validar judge + integración)
    - Validación offline con outputs pre-generados
    """
    context = get_match_context(conn, fixture_id)
    if not context:
        return {"error": f"fixture {fixture_id} not found", "fixture_id": fixture_id}
    
    numerico_report = run_numerico_real(context)
    
    judge_output = judge_from_dicts(
        {
            "bull_local": bull_output,
            "bear_visitante": bear_output,
            "numerico": numerico_report,
        },
        match_id=str(fixture_id),
    )
    
    return {
        "fixture_id": fixture_id,
        "match_id": str(fixture_id),
        "context": {
            "home_team": context.get("home_team"),
            "away_team": context.get("away_team"),
            "date": context.get("date"),
            "venue": context.get("venue_name"),
            "result": context.get("result"),
        },
        "agents": {
            "numerico": numerico_report,
            "bull_local": bull_output,
            "bear_visitante": bear_output,
        },
        "judge": judge_output,
        "mode": "live_mock",
        "timestamp": datetime.now().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI: Validar formato de prompts
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Smoke test: imprimir prompts formateados
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=int, required=True)
    args = p.parse_args()
    
    conn = sqlite3.connect(str(DB_PATH))
    context = get_match_context(conn, args.fixture)
    numerico = run_numerico_real(context)
    ensemble_probs = numerico["probs"]
    
    # Inyectar features
    from proyectos.src.agents.feature_block import build_feature_block
    feature_block = build_feature_block(conn, context)
    conn.close()
    
    bull_task = build_bull_task(context, ensemble_probs, args.fixture, feature_block)
    bear_task = build_bear_task(context, ensemble_probs, args.fixture, feature_block)
    
    print("=" * 70)
    print("BULL TASK")
    print("=" * 70)
    print(bull_task)
    print()
    print("=" * 70)
    print("BEAR TASK")
    print("=" * 70)
    print(bear_task)