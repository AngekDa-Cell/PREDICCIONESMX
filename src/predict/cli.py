#!/usr/bin/env python3
"""
predict.py — Interfaz principal para generar pronósticos de Liga MX.

Uso:
  python3 predict.py --home "América" --away "Chivas" --season 2025/2026
  python3 predict.py --home "Pachuca" --away "Tijuana" --matchday 5
  python3 predict.py --fixture 18174226
  python3 predict.py --recent 5
  python3 predict.py --report
  python3 predict.py --validate

Este script es llamado desde el agente (yo) para generar reportes de partido.
"""

import argparse
import json
import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from predict.features import (
    get_team_form, get_full_feature_set, get_head_to_head,
    get_altitude_advantage, get_rest_days, rest_days_advantage,
    get_coach_pressure, get_home_away_split, get_season_context,
    get_attack_defense_strength,
)
from predict.dixon_coles import fit_dixon_coles, predict_from_model
from predict.elo import get_elo_predictions
from predict.heuristics import apply_heuristics, prob_to_odds, find_value_bets, load_manual_narratives, detect_derby
from predict.analyst_log import log_prediction, get_accuracy_report, recent_predictions, ensure_log_schema
from predict.recalibration import apply_calibration, load_calibration
from predict.misc_utils import get_season_id_for_date, load_mx_coefficients


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
DB_PATH = DATA_DIR / "predictions_mx.db"
MANUAL_DIR = DATA_DIR / "manual"
LEAGUE_ID = 743  # Liga MX


# ─────────────────────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"ERROR: Base de datos no encontrada: {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def find_team_by_name(conn: sqlite3.Connection, name: str) -> Optional[sqlite3.Row]:
    """Busca equipo por nombre (búsqueda fuzzy)."""
    search = f"%{name.lower()}%"
    row = conn.execute("""
        SELECT id, name, short_code, venue_id
        FROM teams
        WHERE LOWER(name) LIKE ? OR LOWER(short_code) LIKE ?
        LIMIT 1
    """, (search, search)).fetchone()

    if not row:
        # Try partial match on key terms
        aliases = {
            'américa': 2687, 'club américa': 2687,
            'chivas': 427, 'guadalajara': 427, 'club guadalajara': 427,
            'cruz azul': 2626,
            'pumas': 2989, 'pumas unam': 2989,
            'tigres': 609, 'tigres uanl': 609,
            'rayados': 2662, 'monterrey': 2662,
            'atlas': 680,
            'león': 10836,
            'santos': 2844, 'santos laguna': 2844,
            'pachuca': 10036,
            'toluca': 967,
            'necaxa': 3951,
            'san luis': 15522, 'atlético san luis': 15522,
            'juárez': 6335, 'fc Juárez': 6335,
            'querétaro': 538,
            'puebla': 3849,
            'mazatlán': 247689,
            'tijuana': 11023, 'toros': 11023,
        }
        n = name.lower().strip()
        if n in aliases:
            return conn.execute("SELECT id, name, short_code, venue_id FROM teams WHERE id = ?", (aliases[n],)).fetchone()
    return row


def get_current_season(conn: sqlite3.Connection) -> sqlite3.Row:
    """Obtiene la temporada más reciente."""
    return conn.execute("""
        SELECT id, name FROM seasons
        WHERE league_id = ? AND name LIKE '%/%'
        ORDER BY name DESC LIMIT 1
    """, (LEAGUE_ID,)).fetchone()


def get_season_by_name(conn: sqlite3.Connection, name: str) -> Optional[sqlite3.Row]:
    """Busca temporada por nombre."""
    return conn.execute("""
        SELECT id, name FROM seasons
        WHERE league_id = ? AND name = ?
        LIMIT 1
    """, (LEAGUE_ID, name)).fetchone()


def get_upcoming_fixture(
    conn: sqlite3.Connection,
    home_id: int,
    away_id: int,
    season_id: int
) -> Optional[sqlite3.Row]:
    """Busca el próximo partido entre estos equipos en la temporada."""
    return conn.execute("""
        SELECT id, home_team_id, away_team_id, starting_at, round, matchday
        FROM fixtures
        WHERE league_id = ?
          AND ((home_team_id = ? AND away_team_id = ?)
               OR (home_team_id = ? AND away_team_id = ?))
          AND season_id = ?
          AND home_score IS NULL
        ORDER BY starting_at ASC LIMIT 1
    """, (LEAGUE_ID, home_id, away_id, away_id, home_id, season_id)).fetchone()


def get_latest_fixture(
    conn: sqlite3.Connection,
    home_id: int,
    away_id: int,
    season_id: int
) -> Optional[sqlite3.Row]:
    """Busca el último partido entre estos equipos."""
    return conn.execute("""
        SELECT id, home_team_id, away_team_id, starting_at, round, matchday,
               home_score, away_score
        FROM fixtures
        WHERE league_id = ?
          AND ((home_team_id = ? AND away_team_id = ?)
               OR (home_team_id = ? AND away_team_id = ?))
          AND season_id = ?
          AND home_score IS NOT NULL
        ORDER BY starting_at DESC LIMIT 1
    """, (LEAGUE_ID, home_id, away_id, away_id, home_id, season_id)).fetchone()


# ─────────────────────────────────────────────────────────────────────────────
# REPORT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_prediction(
    conn: sqlite3.Connection,
    home_team_id: int,
    away_team_id: int,
    season_id: int,
    fixture_id: Optional[int] = None,
    fixture_date: Optional[str] = None,
    matchday: Optional[int] = None,
    user_narrative: Optional[str] = None,
    log_to_db: bool = True,
    recalibrate: bool = False,
    min_confidence: float = 0.0,
    use_shrinkage: bool = True,
    is_backtest: bool = False,
) -> Dict[str, Any]:
    """
    Genera un pronóstico completo para el partido.

    Args:
        conn: sqlite3 connection
        home_team_id, away_team_id: IDs de equipos
        season_id: ID de temporada
        fixture_id: ID del fixture si existe en BD
        fixture_date: fecha del partido (para features de rest days)
        user_narrative: narrativa adicional del usuario
        log_to_db: si True, registra en la bitácora
        is_backtest: True si la predicción es retrospectiva (backtest). Se
            guarda con flag is_backtest=1 en BD y NO cuenta para el panel
            de efectividad en el frontend. False para predicciones live.
    """

    # ── 1. Info básica ──────────────────────────────────────────────────
    home_row = conn.execute("SELECT id, name FROM teams WHERE id = ?", (home_team_id,)).fetchone()
    away_row = conn.execute("SELECT id, name FROM teams WHERE id = ?", (away_team_id,)).fetchone()

    if not home_row or not away_row:
        return {"error": "Uno o ambos equipos no encontrados."}

    home_name = home_row['name']
    away_name = away_row['name']

    season_row = conn.execute("SELECT name FROM seasons WHERE id = ?", (season_id,)).fetchone()
    season_name = season_row['name'] if season_row else "Unknown"

    # ── 2. Determinar fecha del partido ─────────────────────────────────
    if not fixture_date:
        if fixture_id:
            f = conn.execute("SELECT starting_at FROM fixtures WHERE id = ?", (fixture_id,)).fetchone()
            if f:
                fixture_date = str(f['starting_at'])
        if not fixture_date:
            fixture_date = datetime.now().isoformat()

    # ── 3. Fit Dixon-Coles ─────────────────────────────────────────────
    model = fit_dixon_coles(conn, season_id, LEAGUE_ID)

    if not model:
        return {"error": "No hay suficientes datos para ajustar el modelo en esta temporada."}

    # ── 4. Features completos ─────────────────────────────────────────
    try:
        features = get_full_feature_set(conn, home_team_id, away_team_id, season_id, fixture_date)
    except Exception as e:
        return {"error": f"Error computando features: {e}"}

    features['home_team_name'] = home_name
    features['away_team_name'] = away_name

    # ── 5. Modelo base ─────────────────────────────────────────────────
    home_alt = features['altitude']['home_altitude'] or 0
    away_alt = features['altitude']['away_altitude'] or 0
    rest_diff = features['rest']['rest_diff']
    form_diff = features['home_form']['momentum'] - features['away_form']['momentum']
    h2h_rate = features['h2h']['a_win_rate']

    dc_output = predict_from_model(
        model,
        home_team_id, away_team_id,
        home_alt, away_alt,
        rest_diff, form_diff, h2h_rate,
    )

    dc_probs = {
        'home_win': dc_output['home_win'],
        'draw': dc_output['draw'],
        'away_win': dc_output['away_win'],
    }

    # ── 6. Narrativas del usuario ─────────────────────────────────────
    narratives = load_manual_narratives(season_name.split('/')[0].strip())
    if user_narrative:
        narratives['narratives'].append({
            'team': home_name,
            'weight': 0.6,
            'direction': 'unknown',
            'description': user_narrative,
            'active': True,
        })

    # ── 7. Aplicar heurísticas ────────────────────────────────────────
    adj_output = apply_heuristics(features, narratives, dc_output)
    adj_probs = {
        'home_win': adj_output['home_win'],
        'draw': adj_output['draw'],
        'away_win': adj_output['away_win'],
    }

    # ── 7.5. Elo Rating ──────────────────────────────────────────────
    # Aplicar shrinkage desde config MX (Fase 6)
    shrinkage = load_mx_coefficients().get("elo_shrinkage", {}).get("factor", 0.7) if use_shrinkage else 1.0
    elo_pred = get_elo_predictions(conn, home_team_id, away_team_id, before_date=fixture_date, shrinkage_factor=shrinkage)
    elo_pred['shrinkage_factor'] = shrinkage

    # ── 7.6. Ensemble final (Elo + DC + heurísticas) ───────────────────
    # Pesos calibrados con backtest 2025
    # Pesos calibrados con backtest Fase 8 (2024-2025, 680 partidos).
    # xG rolling es el modelo individual más fuerte (51.91% acc).
    # Pesos óptimos: xG=0.55, Elo=0.225, DC=0.135, heur=0.09.
    from predict.xg import get_xg_1x2_prediction
    xg_pred = get_xg_1x2_prediction(conn, home_team_id, away_team_id, before_date=fixture_date)
    final_home = (elo_pred['home_win'] * 0.225
                  + dc_probs['home_win'] * 0.135
                  + adj_probs['home_win'] * 0.09
                  + xg_pred['home_win'] * 0.55)
    final_draw = (elo_pred['draw'] * 0.225
                  + dc_probs['draw'] * 0.135
                  + adj_probs['draw'] * 0.09
                  + xg_pred['draw'] * 0.55)
    final_away = (elo_pred['away_win'] * 0.225
                  + dc_probs['away_win'] * 0.135
                  + adj_probs['away_win'] * 0.09
                  + xg_pred['away_win'] * 0.55)

    # Normalizar
    total = final_home + final_draw + final_away
    if total > 0:
        final_home /= total; final_draw /= total; final_away /= total

    # ── 7.7. Recalibración opcional (Platt/Temperature) ─────────────────
    raw_confidence = max(final_home, final_draw, final_away)
    if recalibrate:
        cal_probs = apply_calibration({
            'home_win': final_home,
            'draw': final_draw,
            'away_win': final_away,
        })
        final_home = cal_probs['home_win']
        final_draw = cal_probs['draw']
        final_away = cal_probs['away_win']

    # ── 7.8. Threshold mínimo de confianza ─────────────────────────────
    max_prob = max(final_home, final_draw, final_away)
    confidence_low = max_prob < min_confidence

    # Actualizar adj_probs con ensemble final (post-recalibración)
    adj_probs = {
        'home_win': round(final_home, 4),
        'draw': round(final_draw, 4),
        'away_win': round(final_away, 4),
    }
    adj_output['home_win'] = adj_probs['home_win']
    adj_output['draw'] = adj_probs['draw']
    adj_output['away_win'] = adj_probs['away_win']
    adj_output['elo_diff'] = elo_pred.get('elo_diff', 0)
    adj_output['home_elo'] = elo_pred.get('home_elo', 1500)
    adj_output['away_elo'] = elo_pred.get('away_elo', 1500)
    adj_output['recalibrated'] = recalibrate
    adj_output['min_confidence'] = min_confidence
    adj_output['confidence_low'] = confidence_low
    adj_output['raw_max_prob'] = round(raw_confidence, 4)

    # ── 8. Odd de valore ────────────────────────────────────────────────
    value_bets = find_value_bets(adj_probs)

    # ── 9. Log a BD ─────────────────────────────────────────────────────
    if log_to_db and fixture_id:
        log_prediction(
            conn, fixture_id,
            home_name, away_name, season_name, fixture_date,
            adj_probs, dc_probs,
            (dc_output['predicted_home_goals'], dc_output['predicted_away_goals']),
            adj_output.get('most_likely_score', (0, 0)),
            features, adj_output.get('heuristic_adjustments', []),
            adj_output.get('contrarian_view', ''),
            adj_output.get('is_derby', False),
            (adj_output.get('derby_info') or {}).get('name'),
            adj_output['confidence'],
            is_backtest=is_backtest,
        )

    # ── 10. Armar reporte ──────────────────────────────────────────────
    report = {
        'meta': {
            'home': home_name,
            'away': away_name,
            'season': season_name,
            'fixture_id': fixture_id,
            'matchday': matchday,
            'fixture_date': fixture_date,
            'generated_at': datetime.now().isoformat(),
            'model_confidence': adj_output['confidence'],
            'model_name': 'Ensemble (Elo 22.5% + DC 13.5% + heur 9% + xG 55%)',
            'elo_diff': adj_output.get('elo_diff', 0),
            'home_elo': adj_output.get('home_elo', 1500),
            'away_elo': adj_output.get('away_elo', 1500),
            'recalibrated': adj_output.get('recalibrated', False),
            'min_confidence': adj_output.get('min_confidence', 0.0),
            'confidence_low': adj_output.get('confidence_low', False),
            'max_prob': round(max(adj_probs.values()), 4),
            'raw_max_prob': adj_output.get('raw_max_prob'),
            'shrinkage_factor': shrinkage,
            'home_team_shrink': elo_pred.get('home_team_shrink', 1.0),
            'away_team_shrink': elo_pred.get('away_team_shrink', 1.0),
        },
        'probabilities': {
            '1': {'prob': adj_output['home_win'], 'odds': prob_to_odds(adj_output['home_win']), 'dc': dc_output['home_win']},
            'X': {'prob': adj_output['draw'], 'odds': prob_to_odds(adj_output['draw']), 'dc': dc_output['draw']},
            '2': {'prob': adj_output['away_win'], 'odds': prob_to_odds(adj_output['away_win']), 'dc': dc_output['away_win']},
        },
        'predicted_score': {
            'home_goals': dc_output['predicted_home_goals'],
            'away_goals': dc_output['predicted_away_goals'],
            'most_likely': f"{adj_output.get('most_likely_score', (0, 0))[0]}-{adj_output.get('most_likely_score', (0, 0))[1]}",
            'most_likely_prob': dc_output.get('most_likely_score_prob', 0),
            'top_scores': list(dc_output.get('score_probs', {}).items())[:8],
        },
        'additional_markets': {
            'both_score': dc_output['both_score'],
            'over_2_5': dc_output['over_2_5'],
            'under_2_5': dc_output['under_2_5'],
            'over_2_5_odds': prob_to_odds(dc_output['over_2_5']),
        },
        'key_factors': _summarize_key_factors(features, adj_output),
        'derby': adj_output.get('derby_info') or None,
        'heuristic_adjustments': adj_output.get('heuristic_adjustments', []),
        'contrarian_view': adj_output.get('contrarian_view', ''),
        'value_bets': value_bets,
    }

    return report


def _summarize_key_factors(features: Dict, adj_output: Dict) -> list:
    """Extrae los factores más relevantes del partido."""
    factors = []

    # Altitude
    alt = features.get('altitude', {})
    if alt.get('altitude_diff', 0) >= 1000:
        factors.append({
            'icon': '🏔️', 'factor': 'ALTITUD',
            'detail': f"{int(alt['home_altitude'] or 0)}m local vs {int(alt['away_altitude'] or 0)}m visitante ({alt.get('classification', 'normal')})",
            'impact': 'positive' if alt['altitude_diff'] > 0 else 'negative',
        })

    # Rest days
    rest = features.get('rest', {})
    if rest.get('home_rest_days', 99) < 4:
        factors.append({
            'icon': '😴', 'factor': 'FATIGA LOCAL',
            'detail': f"Solo {rest['home_rest_days']} días de descanso",
            'impact': 'negative',
        })
    if rest.get('away_rest_days', 99) < 4:
        factors.append({
            'icon': '😴', 'factor': 'FATIGA VISITANTE',
            'detail': f"Solo {rest['away_rest_days']} días de descanso",
            'impact': 'negative',
        })

    # Team form
    hf = features.get('home_form', {})
    af = features.get('away_form', {})
    if hf.get('form_str'):
        factors.append({
            'icon': '🔥', 'factor': 'FORMA LOCAL',
            'detail': f"{hf['form_str']} — {hf.get('wins', 0)}W-{hf.get('draws', 0)}D-{hf.get('losses', 0)}L (últimos {hf.get('matches', 0)})",
            'impact': 'positive' if hf.get('momentum', 0) > 1.5 else 'neutral',
        })
    if af.get('form_str'):
        factors.append({
            'icon': '💤', 'factor': 'FORMA VISITANTE',
            'detail': f"{af['form_str']} — {af.get('wins', 0)}W-{af.get('draws', 0)}D-{af.get('losses', 0)}L (últimos {af.get('matches', 0)})",
            'impact': 'negative' if af.get('momentum', 0) < 1.0 else 'neutral',
        })

    # H2H
    h2h = features.get('h2h', {})
    if h2h.get('total', 0) >= 3:
        wr = h2h.get('a_win_rate', 0.5)
        factors.append({
            'icon': '⚔️', 'factor': 'HEAD-TO-HEAD',
            'detail': f"{h2h['a_wins']}-{h2h['draws']}-{h2h['b_wins']} (local: {wr:.0%})",
            'impact': 'positive' if wr > 0.55 else 'neutral',
        })

    # DT pressure
    ch = features.get('coach_home', {})
    ca = features.get('coach_away', {})
    if ch.get('winless_streak', 0) >= 4:
        factors.append({
            'icon': '🔥', 'factor': 'PRESIÓN DT LOCAL',
            'detail': f"{ch.get('winless_streak', 0)} partidos sin ganar",
            'impact': 'negative',
        })
    if ca.get('winless_streak', 0) >= 4:
        factors.append({
            'icon': '💤', 'factor': 'PRESIÓN DT VISITANTE',
            'detail': f"{ca.get('winless_streak', 0)} partidos sin ganar",
            'impact': 'negative',
        })

    # Derby
    if adj_output.get('is_derby'):
        factors.append({
            'icon': '💥', 'factor': 'CLÁSICO / DERBY',
            'detail': f"{adj_output.get('derby_info', {}).get('name', 'Partido de rivalidad')}. Las stats pesan menos.",
            'impact': 'neutral',
        })

    return factors


# ─────────────────────────────────────────────────────────────────────────────
# FORMATTERS — Genera texto legible para enviar a Ángel
# ─────────────────────────────────────────────────────────────────────────────

def format_report(report: Dict) -> str:
    """Genera el reporte final en formato legible para Telegram."""
    if 'error' in report:
        return f"❌ Error: {report['error']}"

    m = report['meta']
    p = report['probabilities']
    ps = report['predicted_score']
    am = report['additional_markets']
    kf = report['key_factors']
    adj = report.get('heuristic_adjustments', [])
    contrarian = report.get('contrarian_view', '')

    # Determine favorite
    fav = '1' if p['1']['prob'] >= max(p['X']['prob'], p['2']['prob']) else \
          '2' if p['2']['prob'] >= p['X']['prob'] else 'X'
    fav_emoji = '🏠' if fav == '1' else '✈️' if fav == '2' else '⚖️'
    fav_name = m['home'] if fav == '1' else m['away'] if fav == '2' else 'EMPATE'

    lines = []

    # ─ Header ──────────────────────────────────────────────────────────
    lines.append(f"⚽ {'─'*40}")
    lines.append(f"  {m['home']} vs {m['away']}")
    if m.get('season'):
        lines.append(f"  📅 {m['season']} | {m.get('matchday', 'N/A')}ª jornada")
    lines.append(f"  🔗 Confianza del modelo: {m['model_confidence']:.0%}")
    # Indicar si fue recalibrado
    if m.get('recalibrated', False):
        lines.append(f"  🔧 Probabilidades RECALIBRADAS (Platt)")
    # Aviso de threshold bajo
    if m.get('confidence_low', False):
        lines.append(f"  ⚠️ Confianza BAJA (<{m.get('min_confidence', 0):.0%}). Modelo no apuesta.")
    lines.append(f"{'─'*42}")

    # ─ Probabilidades 1X2 ──────────────────────────────────────────────
    lines.append(f"\n📊 PRONÓSTICO {m['model_name']}:")
    lines.append(f"  {fav_emoji} {fav_name} es favorito")

    for sel, label in [('1', f'{m["home"][:15]}'), ('X', 'EMPATE'), ('2', f'{m["away"][:15]}')]:
        prob = p[sel]['prob']
        odds = p[sel]['odds']
        bar = '█' * int(prob * 20) + '░' * (20 - int(prob * 20))
        highlight = ' ←' if sel == fav else ''
        lines.append(f"  {sel}: {prob:5.1%}  {bar}  @ {odds:.2f}{highlight}")

    # ─ Elo diff ────────────────────────────────────────────────────────
    elo_diff = m.get('elo_diff', 0)
    home_elo = m.get('home_elo', 1500)
    away_elo = m.get('away_elo', 1500)
    elo_arrow = '🔥' if abs(elo_diff) > 150 else '⭐' if abs(elo_diff) > 50 else '⚖️'
    lines.append(f"\n{elo_arrow} ELO: {m['home']}={home_elo:.0f} vs {m['away']}={away_elo:.0f} (Δ={elo_diff:+.0f})")

    # ─ Marcador predicho ───────────────────────────────────────────────
    lines.append(f"\n⚽ MARCADOR ESTIMADO:")
    lines.append(f"  {m['home']}  {ps['home_goals']} - {ps['away_goals']}  {m['away']}")
    lines.append(f"  Score más probable: {ps['most_likely']} ({ps['most_likely_prob']:.1%})")

    # Top 3 scorelines
    top_scores = report['predicted_score'].get('top_scores', [])[:4]
    if top_scores:
        score_str = ' | '.join([f"{s[0]}: {s[1]:.1%}" for s in top_scores])
        lines.append(f"  Scores top: {score_str}")

    # ─ Mercados adicionales ─────────────────────────────────────────────
    lines.append(f"\n📈 OTROS MERCADOS:")
    bts = '✅' if am['both_score'] > 0.5 else '❌'
    ou = 'O2.5' if am['over_2_5'] > 0.5 else 'U2.5'
    lines.append(f"  {bts} Ambos marcan: {am['both_score']:.1%}")
    lines.append(f"  {ou}: {max(am['over_2_5'], am['under_2_5']):.1%}")

    # ─ Factores clave ────────────────────────────────────────────────────
    if kf:
        lines.append(f"\n🔑 FACTORES CLAVE:")
        for f in kf[:6]:
            sign = '➕' if f['impact'] == 'positive' else '➖' if f['impact'] == 'negative' else '  '
            lines.append(f"  {f['icon']} {f['factor']}: {f['detail']}")

    # ─ Ajustes heurísticos aplicados ────────────────────────────────────
    if adj:
        human_adj = [a for a in adj if a['type'] != 'form_momentum']
        if human_adj:
            lines.append(f"\n🧠 CAPA HUMANA:")
            for a in human_adj[:4]:
                lines.append(f"  • {a['reason']}")

    # ─ Vista contrarian ─────────────────────────────────────────────────
    if contrarian:
        lines.append(f"\n🤔 ÁNGULO CONTRARIO:")
        for c in contrarian.split(' | '):
            if c.strip():
                lines.append(f"  • {c.strip()}")

    # ─ Derby warning ────────────────────────────────────────────────────
    if report.get('derby'):
        d = report['derby']
        lines.append(f"\n🚨 {d['name'].upper()} — {d['description'][:100]}")

    lines.append(f"\n{'─'*42}")
    lines.append(f"  Generado: {datetime.now().strftime('%d/%m %H:%M')} | Liga MX")

    return '\n'.join(lines)


def format_accuracy_report(conn: sqlite3.Connection) -> str:
    """Reporte de accuracy."""
    acc = get_accuracy_report(conn)
    recent = recent_predictions(conn, limit=5)

    lines = ["📈 REPORTE DE PRECISIÓN"]
    lines.append("─" * 36)

    if 'message' in acc:
        lines.append(acc['message'])
        return '\n'.join(lines)

    lines.append(f"Total predicciones: {acc['total_predictions']}")
    lines.append(f"Accuracy 1X2:       {acc['accuracy_1x2']}%")
    lines.append(f"Accuracy BTS:       {acc['accuracy_bts']}%")
    lines.append(f"Accuracy O/U 2.5:   {acc['accuracy_ou_2_5']}%")
    lines.append(f"Confianza promedio: {acc['avg_confidence']:.0%}")
    lines.append("")

    if recent:
        lines.append("Últimas predicciones:")
        for r in recent:
            hit = '✅' if r.get('outcome_hit') == 1 else '❌'
            p = r.get('prediction', {})
            lines.append(f"  {hit} {r['home']} vs {r['away']}: "
                        f"conf={r.get('confidence', 0):.0%} | "
                        f"score_pred={r.get('score_pred', '?')} real={r.get('score_real', '?')}")

    return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Predictions_MX — Pronóstico de Liga MX')
    parser.add_argument('--home', help='Nombre del equipo local')
    parser.add_argument('--away', help='Nombre del equipo visitante')
    parser.add_argument('--season', help='Temporada (ej: 2025/2026). Default: temporada más reciente.')
    parser.add_argument('--matchday', type=int, help='Número de jornada (para contexto)')
    parser.add_argument('--fixture', type=int, help='ID del fixture en la BD')
    parser.add_argument('--narrative', help='Narrativa adicional del usuario')
    parser.add_argument('--recent', type=int, help='Mostrar últimos N partidos con resultados')
    parser.add_argument('--report', action='store_true', help='Reporte de precisión del modelo')
    parser.add_argument('--validate', action='store_true', help='Validar datos en BD')
    parser.add_argument('--json', action='store_true', help='Output JSON puro (para debugging)')
    parser.add_argument('--no-log', action='store_true', help='No registrar en bitácora')
    parser.add_argument('--h2h', action='store_true', help='Solo head-to-head entre equipos')
    parser.add_argument('--recalibrated', action='store_true', help='Aplicar recalibración Platt scaling')
    parser.add_argument('--min-confidence', type=float, default=0.0,
                       help='Threshold mínimo de confianza (0-1). Si max_prob < threshold, marcar como poco confiable')
    parser.add_argument('--no-shrinkage', action='store_true', help='Desactivar shrinkage del Elo (default ON)')

    args = parser.parse_args()

    conn = get_conn()
    ensure_log_schema(conn)

    # ── Validación ────────────────────────────────────────────────────
    if args.validate:
        rows = conn.execute("SELECT COUNT(*) FROM fixtures WHERE league_id = ?", (LEAGUE_ID,)).fetchone()
        teams = conn.execute("SELECT COUNT(*) FROM teams WHERE id IN (SELECT home_team_id FROM fixtures WHERE league_id = ?)", (LEAGUE_ID,)).fetchone()
        seasons = conn.execute("SELECT COUNT(*) FROM seasons WHERE league_id = ?", (LEAGUE_ID,)).fetchone()
        print(f"✅ Validación BD:")
        print(f"   Partidos: {rows[0]}")
        print(f"   Equipos: {teams[0]}")
        print(f"   Temporadas: {seasons[0]}")
        print(f"   DB: {DB_PATH}")
        conn.close()
        return

    # ── Reporte de accuracy ───────────────────────────────────────────
    if args.report:
        print(format_accuracy_report(conn))
        conn.close()
        return

    # ── Partidos recientes ─────────────────────────────────────────────
    if args.recent:
        rows = conn.execute("""
            SELECT f.id, t1.name as home, t2.name as away,
                   f.home_score, f.away_score, f.starting_at, s.name as season
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.id
            JOIN teams t2 ON f.away_team_id = t2.id
            JOIN seasons s ON f.season_id = s.id
            WHERE f.league_id = ? AND f.home_score IS NOT NULL
            ORDER BY f.starting_at DESC LIMIT ?
        """, (LEAGUE_ID, args.recent)).fetchall()

        print(f"⚽ ÚLTIMOS {args.recent} PARTIDOS — Liga MX")
        print("─" * 70)
        for r in rows:
            score = f"{r[3]}-{r[4]}"
            date = str(r[5])[:10]
            print(f"  {date} | {r[1]:20s} {score:6s} {r[2]:20s} | {r[6]}")
        conn.close()
        return

    # ── Head-to-head ──────────────────────────────────────────────────
    if args.h2h and args.home and args.away:
        home_row = find_team_by_name(conn, args.home)
        away_row = find_team_by_name(conn, args.away)
        if not home_row or not away_row:
            print("❌ Equipo(s) no encontrado(s)")
            conn.close()
            return

        season = get_current_season(conn)
        season_id = season['id'] if season else None

        h2h = get_head_to_head(conn, home_row['id'], away_row['id'], limit=20)
        features = get_full_feature_set(conn, home_row['id'], away_row['id'],
                                        season_id, datetime.now().isoformat())

        print(f"⚔️ HEAD-TO-HEAD: {home_row['name']} vs {away_row['name']}")
        print(f"   Balance: {h2h['a_wins']}V - {h2h['draws']}E - {h2h['b_wins']}D "
              f"({h2h['total']} partidos)")
        print(f"   Goles: {h2h['a_goals']} - {h2h['b_goals']}")
        print(f"   Win rate local: {h2h['a_win_rate']:.0%}")

        hf = features['home_form']
        af = features['away_form']
        print(f"\n📊 FORMA RECIENTE:")
        print(f"   {home_row['name']}: {hf['form_str']} ({hf['wins']}W-{hf['draws']}D-{hf['losses']}L) — "
              f"GF:{hf['goals_for']} GA:{hf['goals_against']}")
        print(f"   {away_row['name']}: {af['form_str']} ({af['wins']}W-{af['draws']}D-{af['losses']}L) — "
              f"GF:{af['goals_for']} GA:{af['goals_against']}")

        conn.close()
        return

    # ── Pronóstico principal ───────────────────────────────────────────
    if args.home and args.away:
        home_row = find_team_by_name(conn, args.home)
        away_row = find_team_by_name(conn, args.away)

        if not home_row:
            print(f"❌ Equipo no encontrado: {args.home}")
            conn.close()
            return
        if not away_row:
            print(f"❌ Equipo no encontrado: {args.away}")
            conn.close()
            return

        if args.season:
            season_row = get_season_by_name(conn, args.season)
        else:
            season_row = get_current_season(conn)

        if not season_row:
            print("❌ Temporada no encontrada.")
            conn.close()
            return

        season_id = season_row['id']
        fixture_id = None
        fixture_date = None

        # Buscar fixture upcoming
        upcoming = get_upcoming_fixture(conn, home_row['id'], away_row['id'], season_id)
        if upcoming:
            fixture_id = upcoming['id']
            fixture_date = str(upcoming['starting_at'])
            matchday = upcoming['matchday']
        else:
            # Buscar último partido
            latest = get_latest_fixture(conn, home_row['id'], away_row['id'], season_id)
            if latest and latest['home_score'] is None:
                fixture_id = latest['id']
                fixture_date = str(latest['starting_at'])
                matchday = latest['matchday']
            else:
                matchday = args.matchday

        report = generate_prediction(
            conn, home_row['id'], away_row['id'], season_id,
            fixture_id=fixture_id,
            fixture_date=fixture_date,
            matchday=matchday,
            user_narrative=args.narrative,
            log_to_db=not args.no_log,
            recalibrate=args.recalibrated,
            min_confidence=args.min_confidence,
            use_shrinkage=not args.no_shrinkage,
        )

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        else:
            print(format_report(report))

        conn.close()
        return

    # ── Usage ──────────────────────────────────────────────────────────
    parser.print_help()
    print("\n📌 Ejemplos:")
    print("  python3 predict.py --home 'América' --away 'Chivas'")
    print("  python3 predict.py --home 'Pachuca' --away 'Tijuana' --season 2025/2026")
    print("  python3 predict.py --h2h --home 'Tigres' --away 'Rayados'")
    print("  python3 predict.py --report")
    print("  python3 predict.py --validate")


if __name__ == '__main__':
    main()
