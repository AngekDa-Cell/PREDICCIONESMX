"""
orchestrator.py — Coordina el debate multi-agente (Fase 10.1).

Dos modos:
1. **simulate**: usa simulator.py (sin LLM calls) para backtest rápido
2. **live**: lanza sub-agentes reales con sessions_spawn en paralelo (Fase 10.2)

Restricción dura (Ángel 2026-06-27):
- Plan MiniMax: 3-4 agentes concurrentes máximo
- Agentes NO pueden modificar VPS (toolsAllow estricto)
- Esperar a TODOS antes de consolidar

Fase 10.1: 3 agentes en paralelo (Bull, Bear, Numérico) + Juez (determinista)
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Setup paths para que funcione como módulo y como script standalone
_AGENT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _AGENT_DIR.parent
_PROYECTOS_ROOT = _SRC_DIR.parent.parent  # /workspace
if str(_PROYECTOS_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROYECTOS_ROOT))

# Paths
DATA_DIR = Path(os.environ.get("DATA_DIR", str(_SRC_DIR.parent / "data")))
DB_PATH = DATA_DIR / "predictions_mx.db"
REPORTS_DIR = DATA_DIR / "agent_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_match_context(conn: sqlite3.Connection, fixture_id: int) -> Dict[str, Any]:
    """Obtiene contexto del partido desde la BD."""
    try:
        from .simulator import get_match_context as _get_ctx
    except ImportError:
        from proyectos.src.agents.simulator import get_match_context as _get_ctx  # type: ignore
    return _get_ctx(conn, fixture_id)


def save_report(report: Dict[str, Any], fixture_id: int) -> Path:
    """Guarda el reporte JSON del debate."""
    date_dir = REPORTS_DIR / datetime.now().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    out_path = date_dir / f"fixture_{fixture_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# MODO SIMULATE (backtest)
# ─────────────────────────────────────────────────────────────────────────────

def orchestrate_simulate(
    conn: sqlite3.Connection,
    fixture_id: int,
    save_individual: bool = True,
) -> Dict[str, Any]:
    """
    Modo simulación: debate completo SIN sub-agentes LLM.
    
    Útil para backtest rápido (340 partidos en segundos vs horas con LLM).
    
    Args:
        save_individual: si False, NO escribe JSON por debate
    """
    try:
        from .simulator import simulate_full_debate
    except ImportError:
        from proyectos.src.agents.simulator import simulate_full_debate  # type: ignore
    
    context = get_match_context(conn, fixture_id)
    if not context:
        return {"error": f"fixture {fixture_id} not found", "fixture_id": fixture_id}
    
    debate = simulate_full_debate(context)
    debate["mode"] = "simulate"
    debate["timestamp"] = datetime.now().isoformat()
    
    if save_individual:
        save_report(debate, fixture_id)
    return debate


def orchestrate_batch_simulate(
    conn: sqlite3.Connection,
    fixture_ids: List[int],
    progress: bool = True,
    progress_every: int = 10,
    save_individual: bool = True,
) -> List[Dict[str, Any]]:
    """Ejecuta debate simulado para una lista de fixtures."""
    results = []
    n = len(fixture_ids)
    for i, fid in enumerate(fixture_ids, 1):
        try:
            r = orchestrate_simulate(conn, fid, save_individual=save_individual)
            results.append(r)
            if progress and (i % progress_every == 0 or i == n):
                print(f"  [simulate] {i}/{n} fixtures ({i/n*100:.0f}%)")
        except Exception as e:
            results.append({"error": str(e), "fixture_id": fid})
    return results


# ─────────────────────────────────────────────────────────────────────────────
# MODO LIVE (Fase 10.2 — pendiente)
# ─────────────────────────────────────────────────────────────────────────────

def build_fixture_context_prompt(context: Dict[str, Any]) -> str:
    """Construye el bloque de contexto del partido para inyectar a prompts."""
    return f"""
- Fixture ID: {context.get('fixture_id')}
- Fecha: {context.get('date')}
- Local: {context.get('home_team')} ({context.get('home_team_short')})
- Visitante: {context.get('away_team')} ({context.get('away_team_short')})
- Venue: {context.get('venue_name')} ({context.get('venue_city')})
- Capacidad: {context.get('venue_capacity')}
- Altitud: {context.get('venue_altitude_m')}m
"""


def build_ensemble_probs_prompt(probs: Dict[str, float]) -> str:
    """Construye el bloque de probs del ensemble."""
    return f"""- home_win: {probs.get('home_win', 0.33):.1%}
- draw: {probs.get('draw', 0.34):.1%}
- away_win: {probs.get('away_win', 0.33):.1%}"""


def orchestrate_live(
    conn: sqlite3.Connection,
    fixture_id: int,
    timeout_seconds: int = 240,
) -> Dict[str, Any]:
    """
    Modo LIVE: lanza sub-agentes reales con sessions_spawn.
    
    Delegado a orchestrator_live.py para mantener este módulo
    enfocado en backtest/simulate.
    """
    from .orchestrator_live import orchestrate_live as _live_impl
    return _live_impl(conn, fixture_id, timeout_seconds=timeout_seconds)


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST PILOTO FASE 10.1
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest_pilot(
    n_fixtures: Optional[int] = 30,
    start_date: str = "2025-01-01",
    end_date: str = "2025-12-31",
    random_seed: Optional[int] = 42,
    save_individual_reports: bool = False,
) -> Dict[str, Any]:
    """
    Backtest piloto de Fase 10.1.
    
    Compara:
    - Ensemble numérico solo (baseline)
    - Debate multi-agente (Bull + Bear + Numérico + Juez DWC-MAD)
    
    Args:
        n_fixtures: número de partidos (None = todos en rango)
        start_date, end_date: rango
        random_seed: seed para reproducibilidad
        save_individual_reports: si True, NO guarda cada debate individual
                                 (default False para backtests grandes)
    
    Returns:
        Dict con métricas y comparación.
    """
    import random
    
    conn = sqlite3.connect(str(DB_PATH))
    
    query = """
        SELECT id FROM fixtures
        WHERE league_id = 743
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND starting_at >= ?
          AND starting_at < ?
        ORDER BY starting_at ASC
    """
    fixtures = [row[0] for row in conn.execute(query, (start_date, end_date)).fetchall()]
    
    if random_seed is not None:
        random.seed(random_seed)
        random.shuffle(fixtures)
    
    if n_fixtures:
        fixtures = fixtures[:n_fixtures]
    
    print(f"[backtest_pilot] {len(fixtures)} fixtures en {start_date}..{end_date}")
    
    debates = orchestrate_batch_simulate(
        conn, fixtures,
        progress=True,
        save_individual=save_individual_reports,
    )
    
    # Métricas
    metrics = _compute_metrics(debates)
    
    result = {
        "phase": "10.1",
        "mode": "simulate",
        "n_fixtures": len(fixtures),
        "date_range": [start_date, end_date],
        "random_seed": random_seed,
        "metrics": metrics,
        "metadata": {
            "weights_base": {"numerico": 0.50, "bull_local": 0.25, "bear_visitante": 0.25},
            "judge_algorithm": "DWC-MAD (Dynamic Weighted Consensus)",
        },
    }
    
    # Guardar resumen
    out_path = DATA_DIR / "multi_agent_pilot.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n[backtest_pilot] Resultados guardados en {out_path}")
    return result


def _compute_metrics(debates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calcula accuracy y Brier score para ensemble vs debate."""
    numerico_correct = 0
    judge_correct = 0
    total = 0
    brier_numerico = 0.0
    brier_judge = 0.0
    
    issues_by_type = {}
    
    for d in debates:
        if "error" in d:
            continue
        if "judge" not in d or "agents" not in d:
            continue
        
        # Resultado real
        actual = d.get("context", {}).get("result")
        if actual is None:
            continue
        
        # Predicciones
        numerico = d["agents"]["numerico"]["probs"]
        judge = d["judge"]["final_prediction"]
        
        numerico_pick = max(numerico, key=numerico.get)
        judge_pick = max(judge, key=judge.get)
        
        if numerico_pick == actual:
            numerico_correct += 1
        if judge_pick == actual:
            judge_correct += 1
        
        total += 1
        
        # Brier
        for outcome in ["home_win", "draw", "away_win"]:
            actual_prob = 1.0 if outcome == actual else 0.0
            brier_numerico += (numerico[outcome] - actual_prob) ** 2
            brier_judge += (judge[outcome] - actual_prob) ** 2
        
        # Issues
        for issue in d["judge"].get("issues_found", []):
            t = issue.get("type", "unknown")
            issues_by_type[t] = issues_by_type.get(t, 0) + 1
    
    if total == 0:
        return {"error": "no_valid_fixtures"}
    
    return {
        "n_evaluated": total,
        "numerico_accuracy": round(numerico_correct / total, 4),
        "judge_accuracy": round(judge_correct / total, 4),
        "delta_accuracy_pp": round((judge_correct - numerico_correct) / total * 100, 2),
        "numerico_brier": round(brier_numerico / total, 4),
        "judge_brier": round(brier_judge / total, 4),
        "delta_brier": round((brier_judge - brier_numerico) / total, 4),
        "issues_found": issues_by_type,
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--start", type=str, default="2025-01-01")
    p.add_argument("--end", type=str, default="2025-12-31")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-reports", action="store_true", help="Guardar cada debate individual")
    args = p.parse_args()
    
    result = run_backtest_pilot(
        n_fixtures=args.n,
        start_date=args.start,
        end_date=args.end,
        random_seed=args.seed,
        save_individual_reports=args.save_reports,
    )
    
    print("\n=== RESULTADOS FASE 10.1 PILOTO ===")
    print(json.dumps(result["metrics"], indent=2))
