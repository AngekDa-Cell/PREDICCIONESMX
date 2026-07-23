#!/usr/bin/env python3
"""
Populate `analyst_predictions` con predicciones del ensemble numérico para
todos los partidos próximos (no terminados) de Liga MX.

Esto desbloquea los badges 🤖 IA + ProbabilityBars + ResultIndicator en el
frontend quinielas.lol (frontend lee esta tabla).

Uso:
    cd /workspace/proyectos
    python3 src/predict/populate_analyst_predictions.py [--dry-run]

Output:
    Inserta/actualiza filas en `analyst_predictions` con:
        - home_win, draw, away_win (probabilidades del ensemble)
        - confidence (del ajuste heurístico)
        - predicted_home_goals, predicted_away_goals (goles esperados)
        - most_likely_score (argmax matriz Poisson)
        - key_factors (top features que justifican la predicción)
        - derby_flag, derby_name
        - contrarian_view (heurísticas detectadas)
"""

import sys
import sqlite3
import json
import argparse
from pathlib import Path
from datetime import datetime

# Path setup
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.predict.backtest import predict_match  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no insertar")
    parser.add_argument("--limit", type=int, default=None, help="Solo procesar N partidos")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(db_path))

    # Defensa en profundidad: índice UNIQUE en fixture_id para garantizar
    # que NUNCA pueda haber 2 predicciones para el mismo partido en BD.
    # El UPSERT de abajo aprovecha este índice.
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_analyst_predictions_fixture_unique
        ON analyst_predictions(fixture_id)
    """)
    conn.commit()

    # 1. Obtener partidos próximos (no terminados, próximos 60 días)
    rows = conn.execute("""
        SELECT f.id, f.home_team_id, f.away_team_id, f.season_id, f.starting_at,
               ht.name, at.name
        FROM fixtures f
        JOIN teams ht ON ht.id = f.home_team_id
        JOIN teams at ON at.id = f.away_team_id
        WHERE f.league_id = 743
          AND f.home_score IS NULL
          AND f.starting_at >= datetime('now')
          AND f.starting_at <= datetime('now', '+60 days')
        ORDER BY f.starting_at
    """).fetchall()

    if args.limit:
        rows = rows[: args.limit]

    print(f"📊 Partidos a procesar: {len(rows)}")
    print()

    narratives = {"narratives": [], "derbies": []}

    # 2. Para cada partido, correr el ensemble
    inserts = []
    errors = 0
    for fid, home_id, away_id, season_id, starting_at, home_name, away_name in rows:
        try:
            pred = predict_match(conn, home_id, away_id, season_id, starting_at, narratives)
            if pred is None:
                print(f"  ⚠️  {home_name} vs {away_name}: pred=None")
                continue

            ensemble = pred["ensemble"]
            is_derby = pred.get("is_derby", False)
            derby_info = pred.get("derby_info", None) or {}
            derby_name = derby_info.get("name") if isinstance(derby_info, dict) else None

            # Goles esperados: usar la matriz Poisson real de Dixon-Coles.
            # Antes calculábamos heurística con round() que daba marcadores
            # fake (e.g. pick "Visita" 36.5% con marcador "1-1").
            home_goals = float(pred.get("predicted_home_goals") or 1.4)
            away_goals = float(pred.get("predicted_away_goals") or 1.0)
            home_goals = max(0.2, home_goals)
            away_goals = max(0.2, away_goals)

            # Marcador más probable REAL (argmax de la matriz Poisson DC).
            # DC devuelve tupla (h, a); convertir a string "h-a".
            _mls = pred.get("most_likely_score")
            if isinstance(_mls, (tuple, list)):
                _dc_top_score = f"{int(_mls[0])}-{int(_mls[1])}"
            elif isinstance(_mls, str) and _mls:
                _dc_top_score = _mls
            else:
                _dc_top_score = f"{round(home_goals)}-{round(away_goals)}"

            # *** BUG FIX 2026-07-23: usar la score_probs REAL del DC (con corrección
            # rho para 0-0, 1-0, 0-1, 1-1) en lugar de recalcular Poisson independiente.
            # El bug anterior (líneas 119-127 antes del fix) generaba siempre MLS=1-0
            # o 0-1 porque la Poisson sin rho con goles esperados ~1.0-1.5 siempre tiene
            # argmax en k=1 para ambos equipos. Ahora exponemos dc_score_probs desde
            # predict_match() y la usamos si está disponible.
            _score_probs = {}
            _dc_sp_raw = pred.get("dc_score_probs", {})
            if _dc_sp_raw and isinstance(_dc_sp_raw, dict) and len(_dc_sp_raw) > 0:
                # _dc_sp_raw viene como dict {"h-a": p, ...} del DC. Convertir a tuplas.
                for _k, _v in _dc_sp_raw.items():
                    try:
                        _h_str, _a_str = _k.split("-")
                        _score_probs[(int(_h_str), int(_a_str))] = float(_v)
                    except (ValueError, AttributeError):
                        continue
                # Renormalizar por si acaso (suma debería ser ~1 si DC lo generó bien).
                _total = sum(_score_probs.values())
                if _total > 0:
                    for _k in _score_probs:
                        _score_probs[_k] /= _total
            if not _score_probs:
                # Fallback al bug anterior si dc_score_probs no está disponible.
                import math
                def _poisson(k, lam):
                    return (lam ** k) * math.exp(-lam) / math.factorial(k)
                for _h in range(8):
                    for _a in range(8):
                        _score_probs[(_h, _a)] = _poisson(_h, home_goals) * _poisson(_a, away_goals)
                _total = sum(_score_probs.values())
                for _k in _score_probs:
                    _score_probs[_k] /= _total if _total > 0 else 1.0

            # Derivar 1X2 desde la matriz (ya sea DC o Poisson fallback).
            home_win_p = sum(p for (h, a), p in _score_probs.items() if h > a)
            draw_p     = sum(p for (h, a), p in _score_probs.items() if h == a)
            away_win_p = sum(p for (h, a), p in _score_probs.items() if h < a)
            # Confidence: prob máxima de la matriz (consistente con marcador)
            confidence = max(home_win_p, draw_p, away_win_p)

            # *** PLATT SCALING OVERRIDE (Fase B 2026-07-19) ***
            # Si Platt scaling está activo (data/platt_coefficients.json existe),
            # sobreescribir las probs Poisson-DC con las del ensemble calibrado.
            # Esto usa el modelo combinado (xG + Elo + DC + heur) que ha mostrado
            # mayor accuracy OOS (+0.50pp acc, -0.33pp brier) vs DC puro.
            # El marcador (most_likely_score) sigue viniendo de la Poisson DC
            # por consistencia score↔score. La inconsistencia leve entre
            # probs (ensemble calibrado) y marcador (DC puro) es aceptable
            # porque ambos vienen del mismo modelo base (DC + heurísticas + ensemble).
            ensemble_calibrated = pred.get("ensemble_calibrated")
            ensemble_raw = pred.get("ensemble")
            if (ensemble_calibrated is not None and ensemble_raw is not None
                and ensemble_calibrated is not ensemble_raw):
                # Platt está activo (calibration.py creó un dict nuevo)
                home_win_p = ensemble_calibrated["home"]
                draw_p = ensemble_calibrated["draw"]
                away_win_p = ensemble_calibrated["away"]
                confidence = max(home_win_p, draw_p, away_win_p)

            # *** SCORE CONSISTENTE CON PICK ***
            # El argmax puntual de la matriz (e.g. "1-1") puede diferir del
            # outcome top (e.g. Local 39.6% > Empate 32.8% > Visit 27.6%).
            # Para que score y probs cuenten la misma historia, elegimos el
            # marcador más probable DENTRO del pick (no del max puro):
            #   - Si pick es Local: mejor (h>a) en score_probs
            #   - Si pick es Empate: mejor (h==a) en score_probs
            #   - Si pick es Visit: mejor (h<a) en score_probs
            # BUG FIX 2026-07-23: antes usaba max(home, draw, away) que siempre
            # daba HOME/AWAY (nunca DRAW como pick). Ahora respeta el threshold
            # DRAW >= 0.32 de predict_match().
            _pick_for_score = pred.get('pick') or max(
                {'home': home_win_p, 'draw': draw_p, 'away': away_win_p},
                key={'home': home_win_p, 'draw': draw_p, 'away': away_win_p}.get
            )
            if _pick_for_score == 'home':
                _top_outcome = 'home'
                _top_filter = lambda x: x[0] > x[1]
            elif _pick_for_score == 'away':
                _top_outcome = 'away'
                _top_filter = lambda x: x[0] < x[1]
            else:
                _top_outcome = 'draw'
                _top_filter = lambda x: x[0] == x[1]
            _matching = {k: v for k, v in _score_probs.items() if _top_filter(k)}
            if _matching:
                _top_match = max(_matching, key=_matching.get)
                most_likely = f"{_top_match[0]}-{_top_match[1]}"
            else:
                most_likely = _dc_top_score

            # Key factors (top features detectadas por heurísticas)
            key_factors = []
            if is_derby:
                key_factors.append("Derby regional detectado")
            # Tier del pick (Quick Win A2 + C1)
            tier = pred.get("tier", "low")
            pick = pred.get("pick", None)
            tier_emoji = {"high": "🟢", "medium": "🟡", "low": "⚪"}[tier]
            if tier == "high":
                key_factors.append(f"{tier_emoji} PICK FUERTE — {pick.upper()} {confidence:.0%}")
            elif tier == "medium":
                key_factors.append(f"{tier_emoji} Pick moderado — {pick.upper() if pick else '?'} {confidence:.0%}")
            else:
                key_factors.append(f"{tier_emoji} SIN PICK claro — partido parejo ({confidence:.0%})")
            # BUG FIX (2026-06-30): umbral 0.30 era demasiado bajo (el empate
            # promedio en fútbol ya es 27-30%, así que se disparaba siempre).
            # Subido a 0.40 para que realmente sea "elevado".
            if draw_p > 0.40:
                key_factors.append("Probabilidad de empate elevada")
            if home_win_p > 0.55:
                key_factors.append("Local favorito")
            elif away_win_p > 0.55:
                key_factors.append("Visitante favorito")

            # H2H histórico (SportMonks 10-20 años). BUG FIX 2026-07-23.
            # Antes no aparecía en el reporte — Ángel preguntaba "por qué Atlante?"
            # sin poder ver el H2H. Ahora se imprime si hay ≥6 partidos.
            h2h_info = pred.get("h2h") or {}
            h2h_n = h2h_info.get("total", 0)
            if h2h_n >= 6:
                # a_wins es desde perspectiva del home team (predict_match retorna
                # desde team_a que es home_team_id)
                home_h2h_w = h2h_info.get("a_wins", 0)
                away_h2h_w = h2h_info.get("b_wins", 0)
                h2h_d = h2h_info.get("draws", 0)
                key_factors.append(
                    f"H2H: {h2h_n} partidos ({home_name[:5]} {home_h2h_w}-{h2h_d}-{away_h2h_w})"
                )

            # Contrarian view (heurísticas que sugieren cautela)
            contrarian = []
            if 0.45 < home_win_p < 0.55:
                contrarian.append("Partido muy parejo — local con ligera ventaja")
            if 0.45 < away_win_p < 0.55:
                contrarian.append("Partido muy parejo — visitante con ligera ventaja")
            if confidence < 0.40:
                contrarian.append("Modelo con confianza baja — máxima cautela")

            inserts.append({
                "fixture_id": fid,
                "home_team": home_name,
                "away_team": away_name,
                "season": str(season_id),
                "match_date": starting_at,
                # Probs 1X2 derivadas de la misma Poisson que da el marcador.
                "home_win": round(home_win_p, 4),
                "draw": round(draw_p, 4),
                "away_win": round(away_win_p, 4),
                "confidence": round(confidence, 4),
                # Probs del Dixon-Coles puro (para trazabilidad y análisis).
                # Antes no se guardaban; ahora populate_analyst_predictions.py
                # las expone desde predict_match(). Bug fix 2026-07-23.
                "home_win_dc": pred.get('dc_home_win'),
                "draw_dc": pred.get('dc_draw'),
                "away_win_dc": pred.get('dc_away_win'),
                "predicted_home_goals": home_goals,
                "predicted_away_goals": away_goals,
                "most_likely_score": most_likely,
                "key_factors": " · ".join(key_factors) if key_factors else None,
                "contrarian_view": " · ".join(contrarian) if contrarian else None,
                "derby_flag": 1 if is_derby else 0,
                "derby_name": derby_name,
                "features_used": json.dumps({
                    "ensemble": ensemble,
                    "xg": pred.get("xg"),
                    "elo": pred.get("elo"),
                    "dc": pred.get("dc"),
                    "most_likely_score": most_likely,
                    "score_probs_top10": sorted(_score_probs.items(), key=lambda x: -x[1])[:10],
                }),
                "notes": f"[tier={tier} | pick={pick}] Predicción automática via populate_analyst_predictions.py",
            })

            print(
                f"  ✓ {home_name:25s} vs {away_name:25s} "
                f"→ H:{home_win_p:.1%} D:{draw_p:.1%} A:{away_win_p:.1%} "
                f"conf:{confidence:.0%} {most_likely}"
            )
        except Exception as e:
            errors += 1
            print(f"  ✗ {home_name} vs {away_name}: {e}")

    print()
    print(f"Total: {len(inserts)} predicciones, {errors} errores")

    if args.dry_run or not inserts:
        print("\n[DRY RUN] No se insertó nada.")
        return

    # 3. UPSERT: 1 fila por fixture, siempre la última predicción.
    # Usamos INSERT ... ON CONFLICT para reemplazar la fila anterior
    # si ya existe (aprovechando el UNIQUE INDEX de arriba).
    # Esto garantiza idempotencia: correr el script 2 veces no produce duplicados.
    # is_backtest=0: SIEMPRE live, este script solo corre sobre partidos futuros.
    print(f"\n📝 Insertando/actualizando {len(inserts)} predicciones (is_backtest=0)...")
    cur = conn.cursor()

    for p in inserts:
        cur.execute("""
            INSERT INTO analyst_predictions (
                fixture_id, home_team, away_team, season, match_date,
                home_win, draw, away_win, confidence,
                home_win_dc, draw_dc, away_win_dc,
                predicted_home_goals, predicted_away_goals, most_likely_score,
                key_factors, contrarian_view, derby_flag, derby_name,
                features_used, notes, is_backtest, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
            ON CONFLICT(fixture_id) DO UPDATE SET
                home_team = excluded.home_team,
                away_team = excluded.away_team,
                season = excluded.season,
                match_date = excluded.match_date,
                home_win = excluded.home_win,
                draw = excluded.draw,
                away_win = excluded.away_win,
                confidence = excluded.confidence,
                home_win_dc = excluded.home_win_dc,
                draw_dc = excluded.draw_dc,
                away_win_dc = excluded.away_win_dc,
                predicted_home_goals = excluded.predicted_home_goals,
                predicted_away_goals = excluded.predicted_away_goals,
                most_likely_score = excluded.most_likely_score,
                key_factors = excluded.key_factors,
                contrarian_view = excluded.contrarian_view,
                derby_flag = excluded.derby_flag,
                derby_name = excluded.derby_name,
                features_used = excluded.features_used,
                notes = excluded.notes,
                is_backtest = 0,
                created_at = datetime('now')
        """, (
            p["fixture_id"], p["home_team"], p["away_team"], p["season"], p["match_date"],
            p["home_win"], p["draw"], p["away_win"], p["confidence"],
            p.get("home_win_dc"), p.get("draw_dc"), p.get("away_win_dc"),
            p["predicted_home_goals"], p["predicted_away_goals"], p["most_likely_score"],
            p["key_factors"], p["contrarian_view"], p["derby_flag"], p["derby_name"],
            p["features_used"], p["notes"],
        ))

    conn.commit()
    # Verificación post-insert
    total = conn.execute("SELECT COUNT(*) FROM analyst_predictions").fetchone()[0]
    distinct_fixtures = conn.execute("SELECT COUNT(DISTINCT fixture_id) FROM analyst_predictions").fetchone()[0]
    print(f"  ✅ {len(inserts)} predicciones procesadas")
    print(f"  📊 BD: {total} filas totales, {distinct_fixtures} fixtures distintos")
    assert total == distinct_fixtures, "⚠️  Duplicados detectados!"
    print()
    print("🔗 Frontend mostrará la ÚLTIMA predicción por partido (MAX(created_at)).")
    print("   Script idempotente: correr N veces = mismo resultado final.")


if __name__ == "__main__":
    main()