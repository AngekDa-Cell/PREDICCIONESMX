"""
test_multi_agent.py — Tests para el sistema multi-agente (Fase 10).

Cubre:
- permissions: toolsAllow correcto por rol
- judge: DWC-MAD funciona, ajustes aplicados correctamente
- simulator: simulación produce JSON válido
- orchestrator: batch simulación funciona, métricas se calculan
"""

import sys
import json
import sqlite3
from pathlib import Path
import pytest

# Setup paths
_PROYECTOS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROYECTOS_ROOT))
sys.path.insert(0, str(_PROYECTOS_ROOT / "src"))


# ─────────────────────────────────────────────────────────────────────────────
# PERMISSIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestPermissions:
    def test_bull_local_tools(self):
        from agents.permissions import get_tools_for_role, BULL_LOCAL_TOOLS
        tools = get_tools_for_role("bull_local")
        assert "read" in tools
        assert "memory_search" in tools
        assert "web_search" in tools
        # NO debe tener tools destructivos
        assert "write" not in tools
        assert "edit" not in tools
        assert "gateway" not in tools
        assert "exec" not in tools
        assert tools == BULL_LOCAL_TOOLS

    def test_bear_visitante_tools(self):
        from agents.permissions import get_tools_for_role, BEAR_VISITANTE_TOOLS
        tools = get_tools_for_role("bear_visitante")
        assert tools == BEAR_VISITANTE_TOOLS
        assert "exec" not in tools

    def test_numerico_tools(self):
        from agents.permissions import get_tools_for_role, NUMERICO_TOOLS
        tools = get_tools_for_role("numerico")
        assert "exec" in tools  # Numérico sí puede ejecutar queries
        assert "read" in tools
        assert "write" not in tools

    def test_juez_tools(self):
        from agents.permissions import get_tools_for_role, JUEZ_TOOLS
        tools = get_tools_for_role("juez")
        # Juez es muy restringido
        assert "read" in tools
        assert "memory_get" in tools
        assert "exec" not in tools
        assert "web_search" not in tools

    def test_unknown_role_raises(self):
        from agents.permissions import get_tools_for_role
        with pytest.raises(KeyError):
            get_tools_for_role("nonexistent_role")

    def test_is_tool_allowed(self):
        from agents.permissions import is_tool_allowed
        assert is_tool_allowed("bull_local", "read") is True
        assert is_tool_allowed("bull_local", "exec") is False
        assert is_tool_allowed("numerico", "exec") is True
        assert is_tool_allowed("juez", "exec") is False

    def test_no_agent_can_write(self):
        """Ningún agente debe poder modificar archivos o VPS."""
        from agents.permissions import ROLE_PERMISSIONS
        forbidden = {"write", "edit", "gateway", "process", "cron", "message"}
        for role, tools in ROLE_PERMISSIONS.items():
            for f in forbidden:
                assert f not in tools, f"Rol {role} no debería tener {f}"


# ─────────────────────────────────────────────────────────────────────────────
# JUDGE
# ─────────────────────────────────────────────────────────────────────────────

class TestJudge:
    def test_judge_from_dicts_basic(self):
        from agents.judge import judge_from_dicts
        reports = {
            "numerico": {
                "agent": "numerico",
                "match_id": "1",
                "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2},
                "confidence": 0.6,
            },
            "bull_local": {
                "agent": "bull_local",
                "match_id": "1",
                "team_favored": "Local",
                "win_probability_estimate": 0.55,
                "confidence": 0.6,
            },
            "bear_visitante": {
                "agent": "bear_visitante",
                "match_id": "1",
                "team_favored": "Visitante",
                "win_probability_estimate": 0.30,
                "confidence": 0.5,
            },
        }
        result = judge_from_dicts(reports, match_id="1")
        assert result["judge"] == "dwc_mad_v2"
        assert result["match_id"] == "1"
        assert abs(sum(result["final_prediction"].values()) - 1.0) < 0.01
        assert result["predicted_outcome"] in ["home_win", "draw", "away_win"]
        assert 0 <= result["confidence"] <= 1

    def test_judge_agreement_boosts_qualitative(self):
        """Si Bull y Bear coinciden en favored_team, cualitativos pesan más."""
        from agents.judge import judge_from_dicts
        # Bull y Bear ambos favorecen al local
        reports_agree = {
            "numerico": {"agent": "numerico", "match_id": "1",
                         "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "confidence": 0.6},
            "bull_local": {"agent": "bull_local", "match_id": "1",
                           "team_favored": "Local", "win_probability_estimate": 0.55, "confidence": 0.6},
            "bear_visitante": {"agent": "bear_visitante", "match_id": "1",
                               "team_favored": "Local", "win_probability_estimate": 0.45, "confidence": 0.6},
        }
        result = judge_from_dicts(reports_agree)
        # En acuerdo, numérico pesa menos (0.45 base, baja a 0.35)
        assert result["agents_weights_used"]["numerico"] < 0.45
        assert result["agents_weights_used"]["bull_local"] + result["agents_weights_used"]["bear_visitante"] > 0.40

    def test_judge_disagreement_boosts_numerico(self):
        """Si Bull y Bear discrepan totalmente, numérico pesa más."""
        from agents.judge import judge_from_dicts
        reports_disagree = {
            "numerico": {"agent": "numerico", "match_id": "1",
                         "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "confidence": 0.6},
            "bull_local": {"agent": "bull_local", "match_id": "1",
                           "team_favored": "Local", "win_probability_estimate": 0.55, "confidence": 0.6},
            "bear_visitante": {"agent": "bear_visitante", "match_id": "1",
                               "team_favored": "Visitante", "win_probability_estimate": 0.45, "confidence": 0.6},
        }
        result = judge_from_dicts(reports_disagree)
        # En discrepancia, numérico pesa más (0.55)
        assert result["agents_weights_used"]["numerico"] == 0.55

    def test_judge_low_confidence_penalty(self):
        from agents.judge import judge_from_dicts
        reports = {
            "numerico": {"agent": "numerico", "match_id": "1",
                         "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "confidence": 0.6},
            "bull_local": {"agent": "bull_local", "match_id": "1",
                           "team_favored": "Local", "win_probability_estimate": 0.55, "confidence": 0.2},
            "bear_visitante": {"agent": "bear_visitante", "match_id": "1",
                               "team_favored": "Visitante", "win_probability_estimate": 0.45, "confidence": 0.5},
        }
        result = judge_from_dicts(reports)
        # Bull con confianza < 0.4 → su peso se reduce
        assert result["agents_weights_used"]["bull_local"] < 0.25
        assert any("confianza" in adj.lower() for adj in result["adjustments_applied"])

    def test_judge_probs_sum_to_one(self):
        from agents.judge import judge_from_dicts
        reports = {
            "numerico": {"agent": "numerico", "match_id": "1",
                         "probs": {"home_win": 0.6, "draw": 0.2, "away_win": 0.2}, "confidence": 0.7},
            "bull_local": {"agent": "bull_local", "match_id": "1",
                           "team_favored": "X", "win_probability_estimate": 0.7, "confidence": 0.7},
            "bear_visitante": {"agent": "bear_visitante", "match_id": "1",
                               "team_favored": "Y", "win_probability_estimate": 0.3, "confidence": 0.7},
        }
        result = judge_from_dicts(reports)
        total = sum(result["final_prediction"].values())
        assert abs(total - 1.0) < 0.01

    def test_judge_with_5_agents(self):
        """Fase 10.3: test con 5 agentes (Numérico, Bull, Bear, Contextual, Auditor)."""
        from agents.judge import judge_from_dicts
        reports = {
            "numerico": {"agent": "numerico", "match_id": "1",
                         "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "confidence": 0.7},
            "bull_local": {"agent": "bull_local", "match_id": "1",
                           "team_favored": "Local", "win_probability_estimate": 0.55, "confidence": 0.7},
            "bear_visitante": {"agent": "bear_visitante", "match_id": "1",
                               "team_favored": "Visitante", "win_probability_estimate": 0.25, "confidence": 0.6},
            "contextual": {"agent": "contextual", "match_id": "1",
                           "narrative_signal": "home_advantage",
                           "qualitative_adjustment": 0.05,
                           "adjustment_target": "home_win",
                           "confidence": 0.65},
            "data_auditor": {"agent": "data_auditor", "match_id": "1",
                             "data_quality_score": 0.85, "recommendation": "proceed",
                             "confidence": 0.8},
        }
        result = judge_from_dicts(reports)
        assert result["judge"] == "dwc_mad_v2"
        # Bull y Bear discrepan → numérico pesa 0.55
        assert result["agents_weights_used"]["numerico"] == 0.55
        # Contextual adjustment +0.05 sobre home_win debe aplicarse
        assert any("Contextual qualitative_adjustment" in adj for adj in result["adjustments_applied"])
        # Probs suman 1
        assert abs(sum(result["final_prediction"].values()) - 1.0) < 0.01

    def test_judge_auditor_abort_penalty(self):
        """Fase 10.3: Si auditor recomienda abort, confianza *= 0.5."""
        from agents.judge import judge_from_dicts
        reports = {
            "numerico": {"agent": "numerico", "match_id": "1",
                         "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "confidence": 0.7},
            "bull_local": {"agent": "bull_local", "match_id": "1",
                           "team_favored": "Local", "win_probability_estimate": 0.55, "confidence": 0.7},
            "bear_visitante": {"agent": "bear_visitante", "match_id": "1",
                               "team_favored": "Visitante", "win_probability_estimate": 0.25, "confidence": 0.6},
            "data_auditor": {"agent": "data_auditor", "match_id": "1",
                             "data_quality_score": 0.3, "recommendation": "abort",
                             "confidence": 0.8},
        }
        result = judge_from_dicts(reports)
        # Confidence debe ser <0.35 (original ~0.65 con penalización x0.5)
        assert result["confidence"] < 0.40
        assert any("abort" in adj for adj in result["adjustments_applied"])


# ─────────────────────────────────────────────────────────────────────────────
# AGENT REPORT
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentReport:
    def test_from_dict_numerico(self):
        from agents.judge import AgentReport
        data = {
            "agent": "numerico",
            "match_id": "42",
            "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2},
            "confidence": 0.65,
        }
        report = AgentReport.from_dict(data)
        assert report.agent == "numerico"
        assert report.match_id == "42"
        assert abs(sum(report.probs.values()) - 1.0) < 0.01
        assert report.confidence == 0.65

    def test_from_dict_bull_local(self):
        from agents.judge import AgentReport
        data = {
            "agent": "bull_local",
            "match_id": "42",
            "team_favored": "América",
            "win_probability_estimate": 0.65,
            "confidence": 0.70,
        }
        report = AgentReport.from_dict(data)
        assert report.agent == "bull_local"
        assert report.team_favored == "América"
        # Bull solo da win_prob, debe construir probs
        assert report.probs["home_win"] == 0.65
        assert abs(sum(report.probs.values()) - 1.0) < 0.01

    def test_from_dict_bear_visitante(self):
        from agents.judge import AgentReport
        data = {
            "agent": "bear_visitante",
            "match_id": "42",
            "team_favored": "Toluca",
            "win_probability_estimate": 0.45,
            "confidence": 0.60,
        }
        report = AgentReport.from_dict(data)
        assert report.probs["away_win"] == 0.45
        assert abs(sum(report.probs.values()) - 1.0) < 0.01

    def test_confidence_clamped(self):
        from agents.judge import AgentReport
        data = {"agent": "numerico", "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "confidence": 1.5}
        report = AgentReport.from_dict(data)
        assert report.confidence == 1.0
        data2 = {"agent": "numerico", "probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "confidence": -0.5}
        report2 = AgentReport.from_dict(data2)
        assert report2.confidence == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulator:
    def test_simulate_bull_local_structure(self):
        from agents.simulator import simulate_bull_local
        ctx = {
            "fixture_id": 1,
            "home_team": "América",
            "home_team_short": "AME",
            "away_team": "Chivas",
            "venue_name": "Estadio Azteca",
            "venue_altitude_m": 2240,
            "venue_capacity": 87000,
        }
        probs = {"home_win": 0.55, "draw": 0.25, "away_win": 0.20}
        result = simulate_bull_local(ctx, probs)
        assert result["agent"] == "bull_local"
        assert result["match_id"] == "1"
        assert result["team_favored"] == "América"
        assert result["win_probability_estimate"] >= 0.55  # Sesgo pro-home
        assert isinstance(result["key_arguments"], list)
        assert isinstance(result["risks_acknowledged"], list)
        assert 0 <= result["confidence"] <= 1

    def test_simulate_bear_visitante_structure(self):
        from agents.simulator import simulate_bear_visitante
        ctx = {
            "fixture_id": 2,
            "home_team": "Pumas",
            "home_team_short": "PUM",
            "away_team": "Tigres",
            "away_team_short": "TIG",
        }
        probs = {"home_win": 0.40, "draw": 0.30, "away_win": 0.30}
        result = simulate_bear_visitante(ctx, probs)
        assert result["agent"] == "bear_visitante"
        assert result["team_favored"] == "Tigres"
        assert result["win_probability_estimate"] >= 0.30  # Sesgo pro-away

    def test_get_match_context_returns_real_data(self):
        from agents.simulator import get_match_context
        db_path = _PROYECTOS_ROOT / "data" / "predictions_mx.db"
        if not db_path.exists():
            pytest.skip("BD no disponible")
        conn = sqlite3.connect(str(db_path))
        # Tomar un fixture con resultado
        fid = conn.execute(
            "SELECT id FROM fixtures WHERE league_id=743 AND home_score IS NOT NULL LIMIT 1"
        ).fetchone()[0]
        ctx = get_match_context(conn, fid)
        conn.close()
        assert "home_team" in ctx
        assert "away_team" in ctx
        assert "result" in ctx  # home_win/draw/away_win
        assert ctx["result"] in ["home_win", "draw", "away_win"]


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR (smoke tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestrator:
    def test_orchestrate_simulate_single(self):
        from agents.orchestrator import orchestrate_simulate
        db_path = _PROYECTOS_ROOT / "data" / "predictions_mx.db"
        if not db_path.exists():
            pytest.skip("BD no disponible")
        conn = sqlite3.connect(str(db_path))
        fid = conn.execute(
            "SELECT id FROM fixtures WHERE league_id=743 AND home_score IS NOT NULL LIMIT 1"
        ).fetchone()[0]
        result = orchestrate_simulate(conn, fid, save_individual=False)
        conn.close()
        assert "agents" in result
        assert "judge" in result
        assert "numerico" in result["agents"]
        assert "bull_local" in result["agents"]
        assert "bear_visitante" in result["agents"]
        assert result["judge"]["judge"] == "dwc_mad_v2"

    def test_compute_metrics_returns_valid_structure(self):
        from agents.orchestrator import _compute_metrics
        debates = [
            {
                "context": {"result": "home_win"},
                "agents": {"numerico": {"probs": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}}},
                "judge": {"final_prediction": {"home_win": 0.55, "draw": 0.25, "away_win": 0.20}, "issues_found": []},
            },
            {
                "context": {"result": "away_win"},
                "agents": {"numerico": {"probs": {"home_win": 0.3, "draw": 0.3, "away_win": 0.4}}},
                "judge": {"final_prediction": {"home_win": 0.25, "draw": 0.30, "away_win": 0.45}, "issues_found": []},
            },
        ]
        metrics = _compute_metrics(debates)
        assert "numerico_accuracy" in metrics
        assert "judge_accuracy" in metrics
        assert "delta_accuracy_pp" in metrics
        assert "judge_brier" in metrics
        assert metrics["n_evaluated"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

class TestPrompts:
    def test_bull_prompt_has_placeholders(self):
        from agents.prompts import BULL_LOCAL_PROMPT
        assert "{fixture_context}" in BULL_LOCAL_PROMPT
        assert "{ensemble_probs}" in BULL_LOCAL_PROMPT
        assert "{match_id}" in BULL_LOCAL_PROMPT
        assert "json" in BULL_LOCAL_PROMPT.lower()

    def test_bear_prompt_has_placeholders(self):
        from agents.prompts import BEAR_VISITANTE_PROMPT
        assert "{fixture_context}" in BEAR_VISITANTE_PROMPT
        assert "{ensemble_probs}" in BEAR_VISITANTE_PROMPT

    def test_juez_prompt_mentions_dwc_mad(self):
        from agents.prompts import JUEZ_PROMPT
        assert "DWC" in JUEZ_PROMPT or "Weighted" in JUEZ_PROMPT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
