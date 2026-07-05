"""
contextual.py — Agente Contextual: busca narrativas y psicología del partido vía web.

Rol: Analizar noticias recientes, declaraciones, narrativa del momento. ¿Hay algo
que los números no capturan?

Tools permitidas: web_search, web_fetch, read (solo memoria propia), memory_*

Output: JSON estructurado con narrative_signal, key_news, qualitative_adjustment.

Fase 10.3 (2026-06-27): Agente Contextual completo.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

# Setup paths
_AGENT_DIR = Path(__file__).resolve().parent
_PROYECTOS_ROOT = _AGENT_DIR.parent.parent.parent
if str(_PROYECTOS_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROYECTOS_ROOT))


CONTEXTUAL_PROMPT = """Eres el AGENTE CONTEXTUAL del sistema multi-agente Predictions_MX.

Tu trabajo es buscar NARRATIVAS, NOTICIAS RECIENTES y PSICOLOGÍA que los números
del ensemble numérico NO capturan. Preguntas clave:

- ¿Hay lesiones/bajas de último momento?
- ¿DT confirmó rotación por compromiso internacional?
- ¿Crisis en vestidor (rumores de conflicto)?
- ¿Racha emocional del equipo (derby previo, tragedia, celebración)?
- ¿Declaraciones polémicas de jugadores/DT?
- ¿Motivación especial (último partido antes de liguilla, descenso, debut)?

# Datos del partido

{fixture_context}

# Predicción base del ensemble numérico (ground truth)

{ensemble_probs}

# Tu tarea

1. USA web_search para buscar noticias RECIENTES (últimas 2 semanas) sobre:
   - "<equipo_local> Liga MX [fecha actual]"
   - "<equipo_visitante> Liga MX [fecha actual]"
   - "[equipo_local] vs [equipo_visitante] previa"
   - "[equipo_local] lesión baja"
   - "[equipo_visitante] lesión baja"
   - "[equipo_local] DT declaraciones"

2. USA web_fetch en 1-2 fuentes confiables (ESPN, MedioTiempo, Marca Claro) para confirmar info clave.

3. Identifica el narrative_signal dominante:
   - "home_advantage" (local con momentum, apoyo masivo)
   - "away_upset" (visitante en racha,机遇)
   - "derby_intensity" (clásico / pasional)
   - "rotation_risk" (uno de los equipos rota por priorización)
   - "injury_crisis" (bajas importantes)
   - "neutral" (nada relevante encontrado)

4. Sugiere un qualitative_adjustment al juez (-0.10 a +0.10 sobre la prob del favorito del ensemble).

5. Asigna confidence 0-1 según certeza de la info encontrada.

# Output esperado (JSON estricto)

```json
{
  "agent": "contextual",
  "match_id": "{match_id}",
  "narrative_signal": "home_advantage",
  "key_news": [
    "América alineará equipo alterno por compromiso de Champions Cup (Fuente: ESPN, 2026-06-25)",
    "Tigres con 2 bajas por lesión: Gignac y Aquino (Fuente: MedioTiempo, 2026-06-26)"
  ],
  "searched_sources": ["ESPN", "MedioTiempo"],
  "qualitative_adjustment": -0.05,
  "adjustment_target": "home_win",
  "adjustment_reasoning": "América con equipo alterno reduce probabilidad de victoria visitante",
  "confidence": 0.65,
  "reasoning_summary": "Rotación confirmada de América reduce slight edge visitante. Estadio lleno y racha local mantienen favoritismo Tigres."
}
```

IMPORTANTE:
- SOLO información REAL de fuentes web. NO inventes.
- Si no encuentras nada relevante, narrative_signal="neutral", adjustment=0.0, confidence=0.3.
- qualitative_adjustment es SUGERENCIA al juez, NO tu predicción final.
"""


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def build_contextual_task(context: Dict[str, Any], ensemble_probs: Dict[str, float], fixture_id: int) -> str:
    """Construye el task completo para el agente Contextual."""
    ctx_str = _format_context(context)
    probs_str = _format_probs(ensemble_probs)
    return CONTEXTUAL_PROMPT.format(
        fixture_context=ctx_str,
        ensemble_probs=probs_str,
        match_id=str(fixture_id),
    )


def _format_context(context: Dict[str, Any]) -> str:
    lines = [
        f"- Fixture ID: {context.get('fixture_id')}",
        f"- Fecha del partido: {context.get('date')}",
        f"- Local: {context.get('home_team')} ({context.get('home_team_short')})",
        f"- Visitante: {context.get('away_team')} ({context.get('away_team_short')})",
    ]
    if context.get("venue_name"):
        lines.append(f"- Venue: {context.get('venue_name')}")
    return "\n".join(lines)


def _format_probs(probs: Dict[str, float]) -> str:
    return (
        f"- home_win: {probs.get('home_win', 0.33):.1%}\n"
        f"- draw: {probs.get('draw', 0.34):.1%}\n"
        f"- away_win: {probs.get('away_win', 0.33):.1%}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PARSING (reutiliza de orchestrator_live)
# ─────────────────────────────────────────────────────────────────────────────

def parse_contextual_output(text: str) -> Dict[str, Any]:
    """Parsea el output del agente Contextual."""
    # Reutilizar el parser genérico de orchestrator_live
    from .orchestrator_live import extract_json_from_text
    parsed = extract_json_from_text(text)
    if parsed:
        parsed.setdefault("agent", "contextual")
        return parsed
    
    # Fallback si no hay JSON
    return {
        "agent": "contextual",
        "narrative_signal": "neutral",
        "key_news": [],
        "searched_sources": [],
        "qualitative_adjustment": 0.0,
        "adjustment_target": None,
        "adjustment_reasoning": "No JSON parseable",
        "confidence": 0.30,
        "reasoning_summary": "Fallback: agente no devolvió JSON válido",
        "fallback_used": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sqlite3
    from .simulator import get_match_context, run_numerico_real
    
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=int, required=True)
    args = p.parse_args()
    
    db_path = _PROYECTOS_ROOT / "proyectos" / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(db_path))
    context = get_match_context(conn, args.fixture)
    numerico = run_numerico_real(context)
    conn.close()
    
    task = build_contextual_task(context, numerico["probs"], args.fixture)
    print(task)