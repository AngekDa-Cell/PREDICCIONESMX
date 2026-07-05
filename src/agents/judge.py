"""
judge.py — Algoritmo Dynamic Weighted Consensus (DWC-MAD).

Implementación determinista (sin LLM) del juez para:
1. Modo backtest: rápida validación sobre N partidos
2. Fallback si el agente Juez LLM falla o tarda

Paper respaldo: DWC-MAD (Springer 2025)

Pesos base (Fase 10.3 — 5 agentes):
- Numérico: 0.45 (ground truth cuantitativo, baja slight vs versión anterior)
- Bull-Local: 0.20
- Bear-Visitante: 0.20
- Contextual: 0.10 (nuevo — narrativas vía web)
- Data Auditor: 0.05 (nuevo — confianza bayesiana sobre datos)

Ajustes dinámicos:
- Si Bull y Bear coinciden en favored_team → cualitativos suben, numérico baja
- Si discrepan totalmente → numérico sube
- Si confianza < 0.4 → peso se reduce a la mitad
- Si data_auditor recomienda "abort" → confidence final *= 0.5
- Si Contextual sugiere qualitative_adjustment != 0 → ajustar probs finales
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


# Pesos base
BASE_WEIGHTS = {
    "numerico": 0.45,
    "bull_local": 0.20,
    "bear_visitante": 0.20,
    "contextual": 0.10,
    "data_auditor": 0.05,
}


@dataclass
class AgentReport:
    """Report normalizado de un agente."""
    agent: str
    match_id: str
    probs: Dict[str, float]  # home_win / draw / away_win
    confidence: float
    team_favored: Optional[str] = None  # solo Bull/Bear
    key_arguments: Optional[List[str]] = None
    risks_acknowledged: Optional[List[str]] = None
    reasoning_summary: Optional[str] = None
    # Campos específicos por agente
    qualitative_adjustment: Optional[float] = None  # solo Contextual
    adjustment_target: Optional[str] = None  # solo Contextual
    data_quality_score: Optional[float] = None  # solo Data Auditor
    recommendation: Optional[str] = None  # solo Data Auditor
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentReport":
        """Crea AgentReport desde dict (output JSON del agente)."""
        agent = data.get("agent", "unknown")
        match_id = str(data.get("match_id", ""))
        
        if agent == "numerico":
            probs = data.get("probs", {})
            probs = {
                "home_win": float(probs.get("home_win", 0.33)),
                "draw": float(probs.get("draw", 0.34)),
                "away_win": float(probs.get("away_win", 0.33)),
            }
        elif agent in ("bull_local", "bear_visitante"):
            win_prob = float(data.get("win_probability_estimate", 0.5))
            if agent == "bull_local":
                home_win = win_prob
                remaining = 1.0 - win_prob
                draw = remaining * 0.55
                away_win = remaining * 0.45
            else:
                away_win = win_prob
                remaining = 1.0 - win_prob
                draw = remaining * 0.55
                home_win = remaining * 0.45
            probs = {"home_win": home_win, "draw": draw, "away_win": away_win}
        elif agent == "contextual":
            # Contextual no da probs directas, solo qualitative_adjustment
            # Construir probs neutrales que el juez ajustará
            probs = {"home_win": 0.33, "draw": 0.34, "away_win": 0.33}
        elif agent == "data_auditor":
            # Data Auditor no da probs, solo data_quality_score
            probs = {"home_win": 0.33, "draw": 0.34, "away_win": 0.33}
        else:
            probs = {"home_win": 0.33, "draw": 0.34, "away_win": 0.33}
        
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        
        return cls(
            agent=agent,
            match_id=match_id,
            probs=probs,
            confidence=confidence,
            team_favored=data.get("team_favored"),
            key_arguments=data.get("key_arguments"),
            risks_acknowledged=data.get("risks_acknowledged"),
            reasoning_summary=data.get("reasoning_summary"),
            qualitative_adjustment=data.get("qualitative_adjustment"),
            adjustment_target=data.get("adjustment_target"),
            data_quality_score=data.get("data_quality_score"),
            recommendation=data.get("recommendation"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "match_id": self.match_id,
            "probs": self.probs,
            "confidence": self.confidence,
            "team_favored": self.team_favored,
            "key_arguments": self.key_arguments,
            "risks_acknowledged": self.risks_acknowledged,
            "reasoning_summary": self.reasoning_summary,
            "qualitative_adjustment": self.qualitative_adjustment,
            "adjustment_target": self.adjustment_target,
            "data_quality_score": self.data_quality_score,
            "recommendation": self.recommendation,
        }


def _compute_dynamic_weights(reports: Dict[str, AgentReport]) -> Tuple[Dict[str, float], List[str]]:
    """
    Calcula pesos dinámicos para cada agente.
    
    Retorna (pesos normalizados, ajustes aplicados).
    """
    weights = dict(BASE_WEIGHTS)
    adjustments = []
    
    # Filtrar solo agentes presentes
    present_agents = {k: v for k, v in weights.items() if k in reports}
    if not present_agents:
        return weights, ["no_agents_present"]
    
    # 1. Ajuste por confianza baja
    for agent, report in reports.items():
        if agent in weights and report.confidence < 0.4:
            old_w = weights[agent]
            weights[agent] = old_w * 0.5
            adjustments.append(f"{agent}: confianza {report.confidence:.2f} < 0.4 → peso reducido a la mitad ({old_w:.3f} → {old_w*0.5:.3f})")
    
    # 2. Si Bull y Bear coinciden en favored_team → reforzar cualitativos
    bull = reports.get("bull_local")
    bear = reports.get("bear_visitante")
    if bull and bear and bull.team_favored and bear.team_favored:
        if bull.team_favored == bear.team_favored:
            # Coincidencia → reforzar cualitativos, bajar numérico
            weights["numerico"] = 0.35
            weights["bull_local"] = 0.25
            weights["bear_visitante"] = 0.25
            adjustments.append(
                f"Bull y Bear coinciden en {bull.team_favored} → numérico 0.45→0.35, cualitativos 0.40→0.50"
            )
        elif bull.team_favored != bear.team_favored and bull.team_favored and bear.team_favored:
            # Discrepancia total → numérico pesa más
            weights["numerico"] = 0.55
            weights["bull_local"] = 0.15
            weights["bear_visitante"] = 0.15
            adjustments.append(
                f"Bull favorece {bull.team_favored}, Bear favorece {bear.team_favored} (opuestos) → numérico 0.45→0.55"
            )
    
    # 3. Si Data Auditor recomienda abort → reducir confianza drásticamente (post-procesado)
    auditor = reports.get("data_auditor")
    if auditor and auditor.recommendation == "abort":
        adjustments.append(
            f"Data Auditor recomienda 'abort' (score={auditor.data_quality_score}) → confianza final será multiplicada x0.5"
        )
    
    # 4. Normalizar pesos para que sumen 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    return weights, adjustments


def compute_final_prediction(
    reports: Dict[str, AgentReport],
    match_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aplica DWC-MAD y produce predicción final (Fase 10.3 — 5 agentes).
    
    Args:
        reports: dict agent_name → AgentReport
    
    Returns:
        dict con final_prediction, confidence, agents_weights_used, etc.
    """
    weights, adjustments = _compute_dynamic_weights(reports)
    
    # Promedio ponderado de probs
    final_probs = {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}
    weighted_confidence = 0.0
    total_weight = 0.0
    
    for agent, report in reports.items():
        w = weights.get(agent, 0.0)
        if w > 0:
            for outcome in final_probs:
                final_probs[outcome] += w * report.probs.get(outcome, 0.0)
            weighted_confidence += w * report.confidence
            total_weight += w
    
    # Normalizar probs
    prob_total = sum(final_probs.values())
    if prob_total > 0:
        final_probs = {k: v / prob_total for k, v in final_probs.items()}
    
    # Aplicar qualitative_adjustment del Contextual (si existe)
    contextual = reports.get("contextual")
    if contextual and contextual.qualitative_adjustment is not None:
        adj = float(contextual.qualitative_adjustment)
        target = contextual.adjustment_target
        if target and target in final_probs:
            final_probs[target] = max(0.0, min(1.0, final_probs[target] + adj))
            # Re-normalizar
            p_total = sum(final_probs.values())
            if p_total > 0:
                final_probs = {k: v / p_total for k, v in final_probs.items()}
            adjustments.append(
                f"Contextual qualitative_adjustment {adj:+.3f} sobre '{target}' aplicado"
            )
    
    # Confianza final = confianza ponderada, ajustada por acuerdo entre agentes
    if total_weight > 0:
        base_confidence = weighted_confidence / total_weight
    else:
        base_confidence = 0.5
    
    # Penalizar si hay mucha discrepancia entre agentes
    probs_list = [r.probs for r in reports.values() if r.agent != "data_auditor"]
    if probs_list:
        home_probs = [p.get("home_win", 0.33) for p in probs_list]
        spread = max(home_probs) - min(home_probs)
        if spread > 0.3:
            penalty = min(0.2, (spread - 0.3) * 0.5)
            base_confidence = max(0.1, base_confidence - penalty)
            adjustments.append(f"Discrepancia alta (spread={spread:.2f}) → confianza penalizada -{penalty:.2f}")
    
    # Aplicar penalización del Data Auditor si recomienda abort
    auditor = reports.get("data_auditor")
    if auditor and auditor.recommendation == "abort":
        base_confidence *= 0.5
        adjustments.append(f"Data Auditor 'abort' → confianza final *= 0.5 (ahora {base_confidence:.3f})")
    elif auditor and auditor.data_quality_score is not None:
        # Modulación suave por calidad de datos
        if auditor.data_quality_score < 0.7:
            base_confidence *= 0.8
            adjustments.append(
                f"Data Auditor score {auditor.data_quality_score:.2f} bajo → confianza *= 0.8"
            )
    
    # Predicted outcome
    predicted = max(final_probs, key=final_probs.get)
    
    # Detectar issues
    issues_found = []
    for agent, report in reports.items():
        if report.confidence < 0.3:
            issues_found.append({
                "severity": "low",
                "agent": agent,
                "type": "low_confidence",
                "detail": f"Agente {agent} reporta confianza {report.confidence:.2f} < 0.3",
            })
        if abs(sum(report.probs.values()) - 1.0) > 0.05:
            issues_found.append({
                "severity": "medium",
                "agent": agent,
                "type": "prob_sum_invalid",
                "detail": f"Probs suman {sum(report.probs.values()):.3f}, esperado 1.0",
            })
    
    return {
        "judge": "dwc_mad_v2",
        "match_id": match_id or "",
        "final_prediction": final_probs,
        "predicted_outcome": predicted,
        "confidence": round(base_confidence, 4),
        "agents_weights_used": weights,
        "adjustments_applied": adjustments,
        "discrepancies_noted": [
            f"{r.agent} home_win={r.probs['home_win']:.3f}"
            for r in reports.values()
        ],
        "issues_found": issues_found,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: judge from raw dicts
# ─────────────────────────────────────────────────────────────────────────────

def judge_from_dicts(reports_dict: Dict[str, Dict[str, Any]], match_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience wrapper: recibe dicts raw de agentes y aplica DWC-MAD.
    
    Args:
        reports_dict: {"bull_local": {...}, "bear_visitante": {...}, "numerico": {...}}
    
    Returns:
        Output completo del juez.
    """
    reports = {name: AgentReport.from_dict(data) for name, data in reports_dict.items()}
    return compute_final_prediction(reports, match_id=match_id)
