"""
data_auditor.py — Agente Auditor de Datos: valida integridad antes de predecir.

Rol: Antes de predecir, valida que los datos de entrada sean correctos.
Reporta anomalías (datos faltantes, legacy, outliers). NO corrige nada.

Tools permitidas: exec (SQLite READ ONLY), read, memory_*

Output: JSON con data_quality_score, issues_found, recommendation.

Fase 10.3 (2026-06-27): Agente Auditor completo.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

# Setup paths
_AGENT_DIR = Path(__file__).resolve().parent
_PROYECTOS_ROOT = _AGENT_DIR.parent.parent.parent
if str(_PROYECTOS_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROYECTOS_ROOT))


DATA_AUDITOR_PROMPT = """Eres el AGENTE AUDITOR DE DATOS del sistema multi-agente Predictions_MX.

Tu trabajo es VALIDAR LA INTEGRIDAD de los datos antes de predecir.
NO corriges nada. REPORTAS issues y recomendás acción.

# Datos del partido

{fixture_context}

# Predicción base del ensemble numérico

{ensemble_probs}

# Tu tarea

1. EJECUTA queries SQLite de validación (READ ONLY) sobre la BD predictions_mx:
   - ¿Equipos existen en tabla teams?
   - ¿Fecha válida?
   - ¿Venue con coordenadas? (si aplica)
   - ¿Attendance disponible para este fixture?
   - ¿Datos históricos suficientes (>=10 partidos por equipo)?
   - ¿Outliers sospechosos en features (xG, form)?
   - ¿Coach data actualizado (< 90 días)?
   - ¿Lesiones activas (si la tabla existe)?

2. Detecta anomalías:
   - **missing_data**: feature crítico faltante (attendance, weather, referee)
   - **legacy_data**: información desactualizada (>180 días)
   - **outlier**: valor extremo que merece revisión
   - **inconsistency**: contradicción entre features (e.g., H2H dice 5-0 pero form reciente dice 1-4)

3. Clasifica cada issue por severity:
   - **low**: no afecta predicción
   - **medium**: puede afectar confianza
   - **high**: predicción poco confiable, abortar

4. Calcula data_quality_score (0-1):
   - 1.0 = datos perfectos
   - 0.7-0.9 = algunos gaps pero aceptable
   - 0.4-0.7 = gaps importantes
   - <0.4 = datos insuficientes

5. Recomienda acción:
   - "proceed" (todo OK)
   - "proceed_with_caution" (gaps menores)
   - "abort" (datos insuficientes)

# Output esperado (JSON estricto)

```json
{
  "agent": "data_auditor",
  "match_id": "{match_id}",
  "data_quality_score": 0.85,
  "checks_performed": [
    "teams_exist", "venue_has_coordinates", "attendance_available",
    "historical_data_sufficient", "coach_data_fresh"
  ],
  "issues_found": [
    {
      "severity": "low",
      "type": "missing_data",
      "detail": "Attendance no disponible para este partido (cobertura 99.9% en backtest pero este fixture específico)"
    },
    {
      "severity": "medium",
      "type": "legacy_data",
      "detail": "Coach data del visitante actualizado hace 180 días"
    }
  ],
  "outliers_detected": [],
  "legacy_data_detected": ["coach_tenure_outdated"],
  "recommendation": "proceed_with_caution",
  "confidence": 0.75,
  "reasoning_summary": "Datos mayormente completos. Gaps menores en attendance y coach data. Predicción aceptable con confianza 0.75."
}
```

⚠️ IMPORTANTE:
- SOLO ejecuta queries SELECT (READ ONLY).
- Si no puedes ejecutar queries, marca checks_performed como [] y baja confidence.
- Sé HONESTO: no infles data_quality_score.
"""


def build_data_auditor_task(context: Dict[str, Any], ensemble_probs: Dict[str, float], fixture_id: int) -> str:
    """Construye el task para el agente Auditor."""
    ctx_str = _format_context(context)
    probs_str = _format_probs(ensemble_probs)
    return DATA_AUDITOR_PROMPT.format(
        fixture_context=ctx_str,
        ensemble_probs=probs_str,
        match_id=str(fixture_id),
    )


def _format_context(context: Dict[str, Any]) -> str:
    lines = [
        f"- Fixture ID: {context.get('fixture_id')}",
        f"- Fecha: {context.get('date')}",
        f"- Local: {context.get('home_team')} ({context.get('home_team_short')}) [team_id={context.get('home_team_id')}]",
        f"- Visitante: {context.get('away_team')} ({context.get('away_team_short')}) [team_id={context.get('away_team_id')}]",
    ]
    if context.get("venue_name"):
        lines.append(f"- Venue: {context.get('venue_name')} (id={context.get('venue_id', 'N/A')})")
    return "\n".join(lines)


def _format_probs(probs: Dict[str, float]) -> str:
    return (
        f"- home_win: {probs.get('home_win', 0.33):.1%}\n"
        f"- draw: {probs.get('draw', 0.34):.1%}\n"
        f"- away_win: {probs.get('away_win', 0.33):.1%}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AUDITOR LOCAL (validación sin LLM — para tests y modo rápido)
# ─────────────────────────────────────────────────────────────────────────────

def run_audit_local(conn: sqlite3.Connection, fixture_id: int, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ejecuta validación de datos localmente (sin LLM).
    Útil para tests y para modo fallback.
    """
    checks = []
    issues = []
    score = 1.0
    
    # Check 1: Teams existen
    home_id = context.get("home_team_id")
    away_id = context.get("away_team_id")
    if home_id and away_id:
        home_exists = conn.execute("SELECT 1 FROM teams WHERE id = ?", (home_id,)).fetchone()
        away_exists = conn.execute("SELECT 1 FROM teams WHERE id = ?", (away_id,)).fetchone()
        if home_exists and away_exists:
            checks.append("teams_exist")
        else:
            issues.append({"severity": "high", "type": "missing_data", "detail": f"Teams not found: home={home_id}, away={away_id}"})
            score -= 0.3
    else:
        issues.append({"severity": "high", "type": "missing_data", "detail": "team_id missing"})
        score -= 0.3
    
    # Check 2: Datos históricos suficientes
    if home_id:
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM fixtures WHERE league_id=743 AND home_score IS NOT NULL AND (home_team_id=? OR away_team_id=?)",
                (home_id, home_id),
            ).fetchone()[0]
            if count >= 10:
                checks.append("historical_data_sufficient")
            elif count >= 5:
                issues.append({"severity": "low", "type": "missing_data", "detail": f"Solo {count} partidos históricos para local"})
                score -= 0.05
            else:
                issues.append({"severity": "medium", "type": "missing_data", "detail": f"Solo {count} partidos históricos para local"})
                score -= 0.20
        except Exception as e:
            issues.append({"severity": "low", "type": "query_error", "detail": str(e)})
    
    # Check 3: Attendance
    try:
        att_count = conn.execute(
            "SELECT COUNT(*) FROM match_attendance WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()[0]
        if att_count > 0:
            checks.append("attendance_available")
        else:
            issues.append({"severity": "low", "type": "missing_data", "detail": "Attendance no disponible para este fixture"})
            score -= 0.05
    except Exception:
        issues.append({"severity": "low", "type": "missing_table", "detail": "match_attendance table not present"})
    
    # Check 4: Venue con coordenadas (si aplica)
    try:
        venue_row = conn.execute("""
            SELECT v.id, v.latitude, v.longitude, v.altitude_m
            FROM venues v
            JOIN fixtures f ON f.venue_id = v.id
            WHERE f.id = ?
        """, (fixture_id,)).fetchone()
        if venue_row and venue_row[1] is not None:
            checks.append("venue_has_coordinates")
        elif venue_row:
            issues.append({"severity": "low", "type": "missing_data", "detail": "Venue sin coordenadas"})
            score -= 0.02
    except Exception:
        pass
    
    # Determinar recomendación
    if score >= 0.85:
        rec = "proceed"
    elif score >= 0.65:
        rec = "proceed_with_caution"
    else:
        rec = "abort"
    
    return {
        "agent": "data_auditor",
        "match_id": str(fixture_id),
        "data_quality_score": round(score, 3),
        "checks_performed": checks,
        "issues_found": issues,
        "outliers_detected": [],
        "legacy_data_detected": [],
        "recommendation": rec,
        "confidence": round(min(1.0, score), 3),
        "reasoning_summary": f"Validados {len(checks)} checks, {len(issues)} issues encontrados. Score {score:.2f} → {rec}",
        "mode": "local",
    }


def parse_auditor_output(text: str) -> Dict[str, Any]:
    """Parsea output del agente Auditor."""
    from .orchestrator_live import extract_json_from_text
    parsed = extract_json_from_text(text)
    if parsed:
        parsed.setdefault("agent", "data_auditor")
        parsed.setdefault("mode", "llm")
        return parsed
    
    return {
        "agent": "data_auditor",
        "data_quality_score": 0.5,
        "issues_found": [{"severity": "medium", "type": "no_json", "detail": "Auditor no devolvió JSON"}],
        "recommendation": "proceed_with_caution",
        "confidence": 0.4,
        "fallback_used": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from .simulator import get_match_context, run_numerico_real
    
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=int, required=True)
    args = p.parse_args()
    
    db_path = _PROYECTOS_ROOT / "proyectos" / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(db_path))
    context = get_match_context(conn, args.fixture)
    
    print("=== MODO LOCAL (sin LLM) ===")
    audit = run_audit_local(conn, args.fixture, context)
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    
    print()
    print("=== TASK para LLM ===")
    numerico = run_numerico_real(context)
    task = build_data_auditor_task(context, numerico["probs"], args.fixture)
    print(task[:1500] + "...")
    conn.close()