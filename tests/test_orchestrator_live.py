"""
test_orchestrator_live.py — Tests para orquestador live con sub-agentes LLM.

Cubre:
- Parsing de JSON desde outputs de sub-agentes
- Build de prompts
- Mock de debate completo end-to-end
- Validación de permisos y herramientas
"""

import sys
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

_PROYECTOS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROYECTOS_ROOT))
sys.path.insert(0, str(_PROYECTOS_ROOT / "src"))


# ─────────────────────────────────────────────────────────────────────────────
# PARSING
# ─────────────────────────────────────────────────────────────────────────────

class TestParseAgentOutput:
    def test_extract_json_from_code_block(self):
        from agents.orchestrator_live import extract_json_from_text
        text = """
        Aquí va mi análisis:
        ```json
        {"agent": "bull_local", "team_favored": "América", "win_probability_estimate": 0.6}
        ```
        Espero que sea útil.
        """
        result = extract_json_from_text(text)
        assert result is not None
        assert result["agent"] == "bull_local"
        assert result["win_probability_estimate"] == 0.6

    def test_extract_json_inline(self):
        from agents.orchestrator_live import extract_json_from_text
        text = 'Mi predicción es {"agent": "bear", "win_probability_estimate": 0.4} y nada más.'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["win_probability_estimate"] == 0.4

    def test_extract_json_nested(self):
        from agents.orchestrator_live import extract_json_from_text
        text = """
        {
          "agent": "bull_local",
          "key_arguments": ["arg1", "arg2"],
          "confidence": 0.7
        }
        """
        result = extract_json_from_text(text)
        assert result is not None
        assert result["agent"] == "bull_local"
        assert len(result["key_arguments"]) == 2

    def test_no_json_returns_none(self):
        from agents.orchestrator_live import extract_json_from_text
        text = "Solo texto sin JSON, lo siento."
        result = extract_json_from_text(text)
        assert result is None

    def test_parse_agent_output_finds_latest(self):
        from agents.orchestrator_live import parse_agent_output
        messages = [
            {"role": "user", "content": "analiza este partido"},
            {"role": "assistant", "content": "voy a pensar..."},
            {"role": "assistant", "content": '```json\n{"agent": "bull_local", "win_probability_estimate": 0.55}\n```'},
        ]
        result = parse_agent_output(messages, "bull_local")
        assert result["agent"] == "bull_local"
        assert result["win_probability_estimate"] == 0.55

    def test_parse_agent_output_fallback(self):
        from agents.orchestrator_live import parse_agent_output
        messages = [
            {"role": "assistant", "content": "no devolví JSON válido, sorry"},
        ]
        result = parse_agent_output(messages, "bull_local")
        assert result["fallback_used"] is True
        assert result["agent"] == "bull_local"
        assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptBuilders:
    def test_build_bull_task(self):
        from agents.orchestrator_live import build_bull_task
        context = {
            "fixture_id": 100,
            "date": "2025-09-15",
            "home_team": "América",
            "home_team_short": "AME",
            "away_team": "Chivas",
            "away_team_short": "CHI",
            "venue_name": "Azteca",
            "venue_city": "CDMX",
            "venue_capacity": 87000,
            "venue_altitude_m": 2240,
        }
        probs = {"home_win": 0.55, "draw": 0.25, "away_win": 0.20}
        task = build_bull_task(context, probs, 100, feature_block="FORMA: W-W-L-D-D")
        assert "América" in task
        assert "Chivas" in task
        assert "55.0%" in task
        assert "100" in task
        assert "bull_local" in task.lower()
        assert "FORMA: W-W-L-D-D" in task  # feature block inyectado

    def test_build_bear_task(self):
        from agents.orchestrator_live import build_bear_task
        context = {
            "fixture_id": 200,
            "home_team": "Pumas",
            "home_team_short": "PUM",
            "away_team": "Tigres",
            "away_team_short": "TIG",
        }
        probs = {"home_win": 0.40, "draw": 0.30, "away_win": 0.30}
        task = build_bear_task(context, probs, 200, feature_block="MOMENTUM: 1.5")
        assert "Pumas" in task
        assert "Tigres" in task
        assert "40.0%" in task
        assert "bear_visitante" in task.lower()
        assert "MOMENTUM: 1.5" in task

    def test_build_bull_task_without_features(self):
        """Si no se inyecta feature_block, debe usar placeholder legacy."""
        from agents.orchestrator_live import build_bull_task
        ctx = {"fixture_id": 1, "date": "2025-01-01", "home_team": "A", "away_team": "B"}
        task = build_bull_task(ctx, {"home_win": 0.5, "draw": 0.25, "away_win": 0.25}, 1)
        assert "legacy" in task.lower() or "no inyectadas" in task.lower()


class TestFeatureBlock:
    def test_build_feature_block_returns_string(self):
        from agents.feature_block import build_feature_block
        db_path = _PROYECTOS_ROOT / "data" / "predictions_mx.db"
        if not db_path.exists():
            pytest.skip("BD no disponible")
        conn = sqlite3.connect(str(db_path))
        fid = conn.execute(
            "SELECT id FROM fixtures WHERE league_id=743 AND home_score IS NOT NULL LIMIT 1"
        ).fetchone()[0]
        from agents.simulator import get_match_context
        ctx = get_match_context(conn, fid)
        block = build_feature_block(conn, ctx)
        conn.close()
        assert isinstance(block, str)
        assert len(block) > 100
        # Debe incluir secciones esperadas
        assert "Forma reciente" in block or "forma" in block.lower()
        assert "Momentum" in block or "momentum" in block.lower()


# ─────────────────────────────────────────────────────────────────────────────
# MOCK ORCHESTRATION
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestrateLiveMock:
    def test_mock_debate_end_to_end(self):
        from agents.orchestrator_live import orchestrate_live_mock
        db_path = _PROYECTOS_ROOT / "data" / "predictions_mx.db"
        if not db_path.exists():
            pytest.skip("BD no disponible")
        
        conn = sqlite3.connect(str(db_path))
        fid = conn.execute(
            "SELECT id FROM fixtures WHERE league_id=743 AND home_score IS NOT NULL LIMIT 1"
        ).fetchone()[0]
        
        # Simular outputs de Bull y Bear (como si vinieran de sub-agentes LLM)
        bull_output = {
            "agent": "bull_local",
            "match_id": str(fid),
            "team_favored": "América",
            "win_probability_estimate": 0.62,
            "key_arguments": [
                "Local invicto en últimos 5",
                "Estadio lleno",
                "H2H favorable",
            ],
            "risks_acknowledged": ["Visitante en racha"],
            "confidence": 0.70,
            "reasoning_summary": "El local tiene argumentos sólidos.",
        }
        bear_output = {
            "agent": "bear_visitante",
            "match_id": str(fid),
            "team_favored": "Toluca",
            "win_probability_estimate": 0.35,
            "key_arguments": ["Visitante en racha de 4 victorias"],
            "risks_acknowledged": ["Público local intenso"],
            "confidence": 0.55,
            "reasoning_summary": "El visitante tiene chances.",
        }
        
        result = orchestrate_live_mock(conn, fid, bull_output, bear_output)
        conn.close()
        
        assert "judge" in result
        assert result["mode"] == "live_mock"
        assert result["judge"]["judge"] == "dwc_mad_v2"
        # Bull favorece América, Bear Toluca → opuestos → numérico pesa más (0.55 en DWC-MAD v2)
        assert result["judge"]["agents_weights_used"]["numerico"] == 0.55

    def test_mock_debate_with_json_arguments_in_text(self):
        """Simula que Bull devuelve JSON embebido en texto natural."""
        from agents.orchestrator_live import parse_agent_output
        
        messages = [
            {
                "role": "assistant",
                "content": """Después de analizar el partido, mi conclusión es:
                
```json
{
  "agent": "bull_local",
  "match_id": "500",
  "team_favored": "Cruz Azul",
  "win_probability_estimate": 0.58,
  "key_arguments": ["Local fuerte", "H2H favorable"],
  "confidence": 0.72
}
```
                
Espero que ayude.""",
            }
        ]
        result = parse_agent_output(messages, "bull_local")
        assert result["team_favored"] == "Cruz Azul"
        assert result["win_probability_estimate"] == 0.58
        assert result["confidence"] == 0.72


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION: Verificar permisos correctos para sub-agentes
# ─────────────────────────────────────────────────────────────────────────────

class TestLivePermissions:
    def test_bull_gets_correct_tools(self):
        """Bull solo debe recibir tools de lectura, no exec destructivo."""
        from agents.permissions import get_tools_for_role
        tools = get_tools_for_role("bull_local")
        assert "read" in tools
        assert "memory_search" in tools
        assert "web_search" in tools
        # CRÍTICO: NO debe tener
        assert "exec" not in tools
        assert "write" not in tools
        assert "gateway" not in tools

    def test_bear_gets_correct_tools(self):
        from agents.permissions import get_tools_for_role
        tools = get_tools_for_role("bear_visitante")
        assert "exec" not in tools
        assert "write" not in tools

    def test_numerico_has_exec_but_constrained(self):
        """Numérico puede ejecutar pero NO debe tener tools destructivos de VPS."""
        from agents.permissions import get_tools_for_role
        tools = get_tools_for_role("numerico")
        assert "exec" in tools  # puede ejecutar ensemble
        assert "gateway" not in tools  # no puede tocar gateway
        assert "write" not in tools  # no puede escribir archivos


# ─────────────────────────────────────────────────────────────────────────────
# LIVE MODE: Verificar que retorna error claro fuera de runtime
# ─────────────────────────────────────────────────────────────────────────────

class TestLiveModeRuntimeCheck:
    def test_live_returns_error_outside_runtime(self):
        """Sin sessions_spawn importable, debe retornar error claro."""
        from agents.orchestrator_live import orchestrate_live
        import builtins
        
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name in ("sessions_spawn", "sessions_yield"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)
        
        db_path = _PROYECTOS_ROOT / "data" / "predictions_mx.db"
        if not db_path.exists():
            pytest.skip("BD no disponible")
        
        conn = sqlite3.connect(str(db_path))
        fid = conn.execute(
            "SELECT id FROM fixtures WHERE league_id=743 AND home_score IS NOT NULL LIMIT 1"
        ).fetchone()[0]
        
        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = orchestrate_live(conn, fid)
        
        conn.close()
        
        assert "error" in result
        assert result["error"] == "not_in_openclaw_runtime"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])