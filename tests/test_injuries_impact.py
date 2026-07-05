#!/usr/bin/env python3
"""
test_injuries_impact.py — Tests para get_player_injuries_impact()

Cubre:
- Sin lesiones → available=False, total_impact=0
- Lesiones Out, Doubtful, Questionable, Day-To-Day
- Importancia por posición (GK > FWD > MID > DEF)
- is_starter fallback cuando minutes_played es NULL
- Múltiples lesiones acumulan
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.predict.features import get_player_injuries_impact


def mock_conn(injuries_rows, minutes_row=None):
    """Factory de mock_conn que maneja execute según la query."""
    def execute_side_effect(q, params=None):
        m = MagicMock()
        q_lower = q.lower() if isinstance(q, str) else ""
        if "player_injuries" in q_lower and "join" in q_lower:
            m.fetchall.return_value = injuries_rows
        elif "fixture_lineups" in q_lower or "avg_min" in q_lower:
            m.fetchone.return_value = minutes_row
        else:
            m.fetchall.return_value = []
            m.fetchone.return_value = None
        return m
    conn = MagicMock()
    conn.execute.side_effect = execute_side_effect
    return conn


def make_injury_row(player_id, team_id, severity, position="MID",
                     full_name="Test Player", common_name=None):
    """Row simulando: id, player_id, severity, injury_type, start_date, meta_json, pos_p, pos_s, full_name, common_name"""
    return (
        1,                    # pi.id
        player_id,            # pi.player_id
        severity,             # pi.severity
        "Muscle",             # pi.injury_type
        "2026-06-20",         # pi.start_date
        "{}",                 # pi.meta_json
        position,              # p.primary_position
        None,                 # p.secondary_position
        full_name,            # p.full_name
        common_name or full_name,  # p.common_name
    )


class TestNoInjuries:
    """Test baseline: sin lesiones."""

    def test_no_injuries_returns_zero_impact(self):
        conn = mock_conn([])
        result = get_player_injuries_impact(conn, team_id=2687)
        assert result["total_impact"] == 0.0
        assert result["available"] == False
        assert result["players_out"] == 0


class TestSeverityOrdering:
    """Out > Doubtful > Questionable > Day-To-Day."""

    def _call(self, severity):
        row = make_injury_row(100, 2687, severity, "MID")
        conn = mock_conn([row], minutes_row=(45.0, 3, 5))
        return get_player_injuries_impact(conn, team_id=2687)["total_impact"]

    def test_ordering(self):
        out = self._call("Out")
        doubt = self._call("Doubtful")
        ques = self._call("Questionable")
        dtd = self._call("Day-To-Day")
        assert out > doubt > ques > dtd, f"{out} > {doubt} > {ques} > {dtd}"

    def test_out_gk_maximum_impact(self):
        row = make_injury_row(100, 2687, "Out", "GK")
        conn = mock_conn([row], minutes_row=(75.0, 8, 10))
        result = get_player_injuries_impact(conn, team_id=2687)
        assert result["total_impact"] >= 0.60, f"Out GK should be >= 0.60, got {result['total_impact']}"


class TestPositionWeights:
    """GK > FWD > MID > DEF (en severidad igual)."""

    def _call(self, position):
        row = make_injury_row(100, 2687, "Out", position)
        conn = mock_conn([row], minutes_row=(60.0, 6, 10))
        return get_player_injuries_impact(conn, team_id=2687)["total_impact"]

    def test_gk_higher_than_fwd(self):
        assert self._call("GK") > self._call("FWD")

    def test_gk_higher_than_mid(self):
        assert self._call("GK") > self._call("MID")

    def test_fwd_higher_than_def(self):
        fwd = self._call("FWD")
        df = self._call("DEF")
        assert fwd > df, f"FWD({fwd}) > DEF({df}): FWD debe pesar más que DEF"


class TestStarterVsSubstitute:
    """is_starter=TRUE tiene mayor impacto que FALSE."""

    def _call(self, avg_min, starts, games):
        row = make_injury_row(100, 2687, "Out", "MID")
        conn = mock_conn([row], minutes_row=(avg_min, starts, games))
        return get_player_injuries_impact(conn, team_id=2687)["total_impact"]

    def test_starter_higher_than_susbtitute(self):
        starter = self._call(75.0, 8, 10)    # 83% → 0.85 factor
        sub = self._call(20.0, 2, 10)         # 20% → 0.30 factor
        assert starter > sub, f"Starter({starter}) > Sub({sub})"


class TestMinutesFallback:
    """NULL minutes → usa ratio de titularidades."""

    def test_null_avg_minutes_uses_starter_ratio(self):
        row = make_injury_row(100, 2687, "Out", "MID")
        conn = mock_conn([row], minutes_row=(45.0, 8, 10))
        result = get_player_injuries_impact(conn, team_id=2687)
        # Out(1.0) * MID(0.50) * 0.80(starter_ratio) = 0.40
        assert 0.15 < result["total_impact"] < 0.6

    def test_no_minutes_row_uses_default_05(self):
        row = make_injury_row(100, 2687, "Out", "MID")
        conn = mock_conn([row], minutes_row=None)  # sin historial
        result = get_player_injuries_impact(conn, team_id=2687)
        # Out(1.0) * MID(0.50) * 0.50(default) = 0.25
        assert 0.1 < result["total_impact"] < 0.5


class TestMultipleInjuries:
    """Múltiples lesiones acumulan más que una sola."""

    def test_three_injuries_more_than_one(self):
        rows = [
            make_injury_row(100, 2687, "Out", "GK"),
            make_injury_row(101, 2687, "Out", "DEF"),
            make_injury_row(102, 2687, "Doubtful", "FWD"),
        ]
        conn = mock_conn(rows, minutes_row=(60.0, 6, 10))
        multi = get_player_injuries_impact(conn, team_id=2687)["total_impact"]

        conn2 = mock_conn([rows[0]], minutes_row=(60.0, 6, 10))
        single = get_player_injuries_impact(conn2, team_id=2687)["total_impact"]

        assert multi > single


class TestPlayersOutCount:
    """players_out refleja el número correcto de lesionados."""

    def test_count_matches_rows(self):
        rows = [
            make_injury_row(100, 2687, "Out", "MID"),
            make_injury_row(101, 2687, "Questionable", "DEF"),
        ]
        conn = mock_conn(rows, minutes_row=(45.0, 4, 5))
        result = get_player_injuries_impact(conn, team_id=2687)
        assert result["players_out"] == 2


class TestKeyPlayersOut:
    """key_players_out cuenta lesionados con importance > 0.4."""

    def test_key_players_gk_out(self):
        row = make_injury_row(100, 2687, "Out", "GK")
        conn = mock_conn([row], minutes_row=(75.0, 8, 10))
        result = get_player_injuries_impact(conn, team_id=2687)
        assert result["key_players_out"] == 1

    def test_non_key_day_to_day_sub(self):
        row = make_injury_row(100, 2687, "Day-To-Day", "DEF", full_name="Suplente")
        conn = mock_conn([row], minutes_row=(20.0, 1, 5))
        result = get_player_injuries_impact(conn, team_id=2687)
        assert result["key_players_out"] == 0