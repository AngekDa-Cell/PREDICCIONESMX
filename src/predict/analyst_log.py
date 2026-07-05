"""
analyst_log.py — Sistema de bitácora del analista.

Registra cada predicción con razonamiento completo.
Permite aprender de los aciertos/errores.
"""

import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path


def ensure_log_schema(conn: sqlite3.Connection):
    """Crea la tabla de log si no existe."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyst_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            fixture_id INTEGER,
            home_team TEXT,
            away_team TEXT,
            season TEXT,
            match_date TEXT,
            -- Probabilidades finales (con heurísticas)
            home_win REAL,
            draw REAL,
            away_win REAL,
            confidence REAL,
            -- Probabilidades base (Dixon-Coles)
            home_win_dc REAL,
            draw_dc REAL,
            away_win_dc REAL,
            -- Predicción de goles
            predicted_home_goals REAL,
            predicted_away_goals REAL,
            most_likely_score TEXT,
            -- Análisis cualitativo
            key_factors TEXT,          -- JSON array de factores clave
            heuristic_adjustments TEXT, -- JSON array de ajustes heurísticos
            contrarian_view TEXT,
            derby_flag INTEGER,
            derby_name TEXT,
            -- Features relevantes
            features_used TEXT,         -- JSON con summary de features
            -- Resultado real (llenado después)
            actual_home_goals INTEGER,
            actual_away_goals INTEGER,
            result_recorded_at TEXT,
            -- Evaluación
            score_hit INTEGER,         -- 1 = acierto exacto
            outcome_hit INTEGER,        -- 1 = acierto 1X2
            bts_hit INTEGER,           -- 1 = both scored
            ou_2_5_hit INTEGER,        -- 1 = over/under pegó
            notes TEXT,
            -- Tipo de predicción: 0 = live (generada antes del partido),
            --                     1 = backtest (generada retrospectivamente)
            is_backtest INTEGER DEFAULT 0,
            UNIQUE(fixture_id)
        )
    """)
    conn.commit()


def log_prediction(
    conn: sqlite3.Connection,
    fixture_id: int,
    home_team: str,
    away_team: str,
    season: str,
    match_date: str,
    adj_probs: Dict[str, float],
    dc_probs: Dict[str, float],
    predicted_goals: tuple,
    most_likely_score: tuple,
    features_summary: Dict[str, Any],
    heuristic_adjustments: List[Dict],
    contrarian_view: str,
    derby_flag: bool,
    derby_name: Optional[str],
    confidence: float,
    is_backtest: bool = False,
) -> int:
    """Registra una predicción en la bitácora.

    Args:
        is_backtest: True si la predicción es retrospectiva (generada después
            del partido, ej. en un backtest). False para predicciones live
            generadas antes del partido. Las BT no cuentan para el panel de
            efectividad en el frontend.
    """
    ensure_log_schema(conn)

    factors = []
    if features_summary.get('home_form', {}).get('form_str'):
        factors.append({
            'type': 'team_form',
            'home': features_summary.get('home_form', {}).get('form_str', ''),
            'away': features_summary.get('away_form', {}).get('form_str', ''),
        })
    if features_summary.get('altitude', {}).get('classification'):
        factors.append({
            'type': 'altitude',
            'home_m': features_summary.get('altitude', {}).get('home_altitude'),
            'away_m': features_summary.get('altitude', {}).get('away_altitude'),
            'class': features_summary.get('altitude', {}).get('classification'),
        })
    if features_summary.get('rest'):
        factors.append({
            'type': 'rest',
            'home_days': features_summary.get('rest', {}).get('home_rest_days'),
            'away_days': features_summary.get('rest', {}).get('away_rest_days'),
        })
    if features_summary.get('h2h', {}).get('total', 0) >= 3:
        factors.append({
            'type': 'h2h',
            'record': f"{features_summary['h2h']['a_wins']}-{features_summary['h2h']['draws']}-{features_summary['h2h']['b_wins']}",
        })

    try:
        conn.execute("""
            INSERT OR REPLACE INTO analyst_predictions (
                fixture_id, home_team, away_team, season, match_date,
                home_win, draw, away_win, confidence,
                home_win_dc, draw_dc, away_win_dc,
                predicted_home_goals, predicted_away_goals, most_likely_score,
                key_factors, heuristic_adjustments, contrarian_view,
                derby_flag, derby_name, features_used, is_backtest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fixture_id, home_team, away_team, season, match_date,
            adj_probs['home_win'], adj_probs['draw'], adj_probs['away_win'], confidence,
            dc_probs['home_win'], dc_probs['draw'], dc_probs['away_win'],
            predicted_goals[0], predicted_goals[1], f"{most_likely_score[0]}-{most_likely_score[1]}",
            json.dumps(factors, ensure_ascii=False),
            json.dumps(heuristic_adjustments, ensure_ascii=False),
            contrarian_view,
            1 if derby_flag else 0,
            derby_name,
            json.dumps(features_summary, ensure_ascii=False, default=str),
            1 if is_backtest else 0,
        ))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except Exception as e:
        print(f"WARNING: Could not log prediction: {e}")
        return -1


def record_result(
    conn: sqlite3.Connection,
    fixture_id: int,
    actual_home_goals: int,
    actual_away_goals: int,
    notes: Optional[str] = None
):
    """Llena el resultado real de un partido ya predicho."""
    home_score = actual_home_goals
    away_score = actual_away_goals

    # Score exacto
    score_hit = 1 if False else 0  # Will be computed properly

    # Outcome
    pred_row = conn.execute(
        "SELECT home_win, draw, away_win FROM analyst_predictions WHERE fixture_id = ?",
        (fixture_id,)
    ).fetchone()

    if not pred_row:
        return

    # 1X2 predicho
    if pred_row[0] >= pred_row[1] and pred_row[0] >= pred_row[2]:
        predicted_outcome = 'home'
    elif pred_row[2] >= pred_row[0] and pred_row[2] >= pred_row[1]:
        predicted_outcome = 'away'
    else:
        predicted_outcome = 'draw'

    # 1X2 real
    if home_score > away_score:
        actual_outcome = 'home'
    elif away_score > home_score:
        actual_outcome = 'away'
    else:
        actual_outcome = 'draw'

    outcome_hit = 1 if predicted_outcome == actual_outcome else 0

    # BTS
    bts_hit = 1 if home_score > 0 and away_score > 0 else 0

    # O/U 2.5
    ou_2_5_hit = 1 if (home_score + away_score) > 2 else 0

    # Score exacto: predecido vs real
    predicted_score_str = conn.execute(
        "SELECT most_likely_score FROM analyst_predictions WHERE fixture_id = ?", (fixture_id,)
    ).fetchone()
    score_hit = 0
    if predicted_score_str and predicted_score_str[0]:
        try:
            ph, pa = map(int, predicted_score_str[0].split('-'))
            score_hit = 1 if ph == home_score and pa == away_score else 0
        except ValueError:
            score_hit = 0

    conn.execute("""
        UPDATE analyst_predictions
        SET actual_home_goals = ?,
            actual_away_goals = ?,
            result_recorded_at = datetime('now'),
            score_hit = ?,
            outcome_hit = ?,
            bts_hit = ?,
            ou_2_5_hit = ?,
            notes = ?
        WHERE fixture_id = ?
    """, (
        home_score, away_score,
        score_hit, outcome_hit, bts_hit, ou_2_5_hit, notes, fixture_id
    ))
    conn.commit()


def get_accuracy_report(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Genera reporte de accuracy de las predicciones."""
    rows = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(outcome_hit) as outcomes,
            SUM(bts_hit) as bts,
            SUM(ou_2_5_hit) as ou,
            AVG(confidence) as avg_confidence
        FROM analyst_predictions
        WHERE outcome_hit IS NOT NULL
    """).fetchone()

    if not rows or rows[0] == 0:
        return {'message': 'Sin predicciones con resultado aún.'}

    total, outcomes, bts, ou, avg_conf = rows

    return {
        'total_predictions': total,
        'accuracy_1x2': round(outcomes / total * 100, 2) if total > 0 else 0,
        'accuracy_bts': round(bts / total * 100, 2) if total > 0 else 0,
        'accuracy_ou_2_5': round(ou / total * 100, 2) if total > 0 else 0,
        'avg_confidence': round(avg_conf, 3) if avg_conf else 0,
        'n': total,
    }


def recent_predictions(
    conn: sqlite3.Connection,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Lista predicciones recientes."""
    rows = conn.execute("""
        SELECT
            fixture_id, home_team, away_team, match_date,
            home_win, draw, away_win, confidence,
            predicted_home_goals, predicted_away_goals, most_likely_score,
            actual_home_goals, actual_away_goals, outcome_hit,
            derby_flag, derby_name
        FROM analyst_predictions
        ORDER BY created_at DESC LIMIT ?
    """, (limit,)).fetchall()

    return [
        {
            'fixture_id': r[0],
            'home': r[1], 'away': r[2], 'date': r[3],
            'prediction': {'home': r[4], 'draw': r[5], 'away': r[6]},
            'confidence': r[7],
            'score_pred': r[10],
            'score_real': f"{r[11]}-{r[12]}" if r[11] is not None else "—",
            'outcome_hit': r[13],
            'derby': r[14], 'derby_name': r[15],
        }
        for r in rows
    ]
