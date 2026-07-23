#!/usr/bin/env python3
"""
populate_backtest_historical.py — Genera predicciones backtest para partidos
históricos con resultado (walk-forward style: usa datos hasta la fecha del partido).

Útil para:
- Validar accuracy real del modelo con muestra grande (>1000 partidos)
- Detectar drift por temporada
- Alimentar Platt scaling / isotonic con más datos OOS
- Backtest de liguilla con stats significativos

Uso:
    cd /workspace/proyectos
    python3 scripts/populate_backtest_historical.py --limit 100
    python3 scripts/populate_backtest_historical.py --seasons 5
    python3 scripts/populate_backtest_historical.py --dry-run

Output:
    Inserta/actualiza filas en analyst_predictions con is_backtest=1.
    Las filas con home_score IS NOT NULL son las que se pueden reconciliar después.
"""

import sys
import sqlite3
import json
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.predict.backtest import predict_match


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no insertar")
    parser.add_argument("--limit", type=int, default=None, help="Solo procesar N partidos")
    parser.add_argument("--seasons", type=int, default=5, help="Cuántas temporadas hacia atrás")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Saltar partidos que ya tienen predicción backtest")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "predictions_mx.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Obtener las últimas N temporadas con resultados
    seasons = conn.execute("""
        SELECT id, name FROM seasons
        WHERE league_id = 743 AND name LIKE '%/%'
        ORDER BY name DESC
        LIMIT ?
    """, (args.seasons,)).fetchall()
    season_ids = [s['id'] for s in seasons]
    print(f"📅 Temporadas a procesar: {[s['name'] for s in seasons]}")

    # Query partidos con resultado de esas temporadas (walk-forward: solo usa datos hasta la fecha)
    query = """
        SELECT f.id, f.home_team_id, f.away_team_id, f.season_id, f.starting_at,
               ht.name, at.name
        FROM fixtures f
        JOIN teams ht ON ht.id = f.home_team_id
        JOIN teams at ON at.id = f.away_team_id
        WHERE f.league_id = 743
          AND f.home_score IS NOT NULL
          AND f.season_id IN ({})
        ORDER BY f.starting_at
    """.format(','.join('?' * len(season_ids)))

    rows = conn.execute(query, season_ids).fetchall()
    print(f"📊 Partidos con resultado: {len(rows)}")

    if args.skip_existing:
        before = len(rows)
        existing = conn.execute("""
            SELECT DISTINCT fixture_id FROM analyst_predictions WHERE is_backtest = 1
        """).fetchall()
        existing_ids = {r['fixture_id'] for r in existing}
        rows = [r for r in rows if r['id'] not in existing_ids]
        print(f"   (saltando {before - len(rows)} ya procesados)")

    if args.limit:
        rows = rows[: args.limit]

    print(f"   (procesando {len(rows)})\n")

    narratives = {"narratives": [], "derbies": []}
    inserts = []
    errors = 0

    for fid, home_id, away_id, season_id, starting_at, home_name, away_name in rows:
        try:
            pred = predict_match(conn, home_id, away_id, season_id, starting_at, narratives)
            if pred is None:
                continue

            # Reconstruir el dict similar al populate live
            ensemble = pred["ensemble"]
            home_goals = float(pred.get("predicted_home_goals") or 1.0)
            away_goals = float(pred.get("predicted_away_goals") or 1.0)
            home_goals = max(0.2, home_goals)
            away_goals = max(0.2, away_goals)

            # MLS
            _mls = pred.get("most_likely_score")
            if isinstance(_mls, (tuple, list)):
                _dc_top_score = f"{int(_mls[0])}-{int(_mls[1])}"
            elif isinstance(_mls, str) and _mls:
                _dc_top_score = _mls
            else:
                _dc_top_score = f"{round(home_goals)}-{round(away_goals)}"

            # Score probs del DC
            _score_probs = {}
            _dc_sp_raw = pred.get("dc_score_probs", {})
            if _dc_sp_raw and isinstance(_dc_sp_raw, dict) and len(_dc_sp_raw) > 0:
                for _k, _v in _dc_sp_raw.items():
                    try:
                        _h_str, _a_str = _k.split("-")
                        _score_probs[(int(_h_str), int(_a_str))] = float(_v)
                    except (ValueError, AttributeError):
                        continue
                _total = sum(_score_probs.values())
                if _total > 0:
                    for _k in _score_probs:
                        _score_probs[_k] /= _total

            home_win_p = sum(p for (h, a), p in _score_probs.items() if h > a)
            draw_p = sum(p for (h, a), p in _score_probs.items() if h == a)
            away_win_p = sum(p for (h, a), p in _score_probs.items() if h < a)
            confidence = max(home_win_p, draw_p, away_win_p)

            # Override con Platt si está activo
            ens_cal = pred.get("ensemble_calibrated")
            ens_raw = pred.get("ensemble")
            if ens_cal is not None and ens_raw is not None and ens_cal is not ens_raw:
                home_win_p = ens_cal["home"]
                draw_p = ens_cal["draw"]
                away_win_p = ens_cal["away"]
                confidence = max(home_win_p, draw_p, away_win_p)

            # Filtro outcome top
            _pick_for_score = pred.get('pick') or max(
                {'home': home_win_p, 'draw': draw_p, 'away': away_win_p},
                key={'home': home_win_p, 'draw': draw_p, 'away': away_win_p}.get
            )
            if _pick_for_score == 'home':
                _top_filter = lambda x: x[0] > x[1]
            elif _pick_for_score == 'away':
                _top_filter = lambda x: x[0] < x[1]
            else:
                _top_filter = lambda x: x[0] == x[1]

            _matching = {k: v for k, v in _score_probs.items() if _top_filter(k)}
            if _matching:
                _top_match = max(_matching, key=_matching.get)
                most_likely = f"{_top_match[0]}-{_top_match[1]}"
            else:
                most_likely = _dc_top_score

            inserts.append({
                "fixture_id": fid,
                "home_team": home_name,
                "away_team": away_name,
                "season": str(season_id),
                "match_date": starting_at,
                "home_win": round(home_win_p, 4),
                "draw": round(draw_p, 4),
                "away_win": round(away_win_p, 4),
                "confidence": round(confidence, 4),
                "home_win_dc": pred.get('dc_home_win'),
                "draw_dc": pred.get('dc_draw'),
                "away_win_dc": pred.get('dc_away_win'),
                "predicted_home_goals": home_goals,
                "predicted_away_goals": away_goals,
                "most_likely_score": most_likely,
            })

            # Print cada 25 partidos (más frecuente para feedback)
            if len(inserts) % 25 == 0:
                print(f"  ... {len(inserts)}/{len(rows)} ({fid=} {home_name[:10]}vs{away_name[:10]} H:{home_win_p:.0%} D:{draw_p:.0%} A:{away_win_p:.0%})")

        except Exception as e:
            errors += 1
            if errors < 5:
                print(f"  ✗ {home_name} vs {away_name}: {e}")

    print(f"\nTotal procesado: {len(inserts)} predicciones, {errors} errores")

    if args.dry_run or not inserts:
        print("\n[DRY RUN] No se insertó nada.")
        return

    # UPSERT — similar al populate live pero con is_backtest=1
    # BUG FIX 2026-07-23: usar executemany en batches grandes (no individual INSERT)
    # para evitar lentitud extrema del UPSERT. Antes: 4+ min para 1370 rows.
    cur = conn.cursor()
    sql = """
        INSERT INTO analyst_predictions (
            fixture_id, home_team, away_team, season, match_date,
            home_win, draw, away_win, confidence,
            home_win_dc, draw_dc, away_win_dc,
            predicted_home_goals, predicted_away_goals, most_likely_score,
            is_backtest, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
        ON CONFLICT(fixture_id) DO UPDATE SET
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
            is_backtest = 1
    """
    rows_data = [
        (p["fixture_id"], p["home_team"], p["away_team"], p["season"], p["match_date"],
         p["home_win"], p["draw"], p["away_win"], p["confidence"],
         p.get("home_win_dc"), p.get("draw_dc"), p.get("away_win_dc"),
         p["predicted_home_goals"], p["predicted_away_goals"], p["most_likely_score"])
        for p in inserts
    ]

    # Commit en batches de 200 para feedback
    batch_size = 200
    total_inserted = 0
    for i in range(0, len(rows_data), batch_size):
        batch = rows_data[i:i+batch_size]
        cur.executemany(sql, batch)
        conn.commit()
        total_inserted += len(batch)
        print(f"  💾 Batch {i//batch_size + 1}: {total_inserted}/{len(rows_data)} insertadas")
    total = conn.execute("SELECT COUNT(*) FROM analyst_predictions WHERE is_backtest = 1").fetchone()[0]
    print(f"✅ {len(inserts)} predicciones backtest insertadas/actualizadas")
    print(f"📊 BD: {total} filas backtest totales")

    # ─────────────────────────────────────────────────────────────────────
    # BUG FIX 2026-07-23: reconciliar outcomes (outcome_hit, score_hit, etc).
    # Antes el script solo insertaba las probs pero nunca llenaba las columnas
    # de "actual_*". Ahora las llena directamente desde la tabla fixtures.
    # ─────────────────────────────────────────────────────────────────────
    print("🔄 Reconciliando outcomes con resultados finales…")
    reconcile_sql = """
        UPDATE analyst_predictions
        SET
            actual_home_goals = f.home_score,
            actual_away_goals = f.away_score,
            outcome_hit = CASE
                WHEN f.home_score IS NULL OR f.away_score IS NULL THEN NULL
                WHEN f.home_score > f.away_score AND home_win >= draw AND home_win >= away_win THEN 1
                WHEN f.away_score > f.home_score AND away_win >= draw AND away_win >= home_win THEN 1
                WHEN f.home_score = f.away_score AND draw >= home_win AND draw >= away_win THEN 1
                ELSE 0
            END,
            score_hit = CASE
                WHEN f.home_score IS NULL OR most_likely_score IS NULL THEN NULL
                WHEN most_likely_score = (CAST(f.home_score AS TEXT) || '-' || CAST(f.away_score AS TEXT)) THEN 1
                ELSE 0
            END,
            bts_hit = CASE
                WHEN f.home_score IS NULL OR f.away_score IS NULL THEN NULL
                WHEN f.home_score > 0 AND f.away_score > 0 THEN 1
                ELSE 0
            END,
            ou_2_5_hit = CASE
                WHEN f.home_score IS NULL OR f.away_score IS NULL THEN NULL
                WHEN (f.home_score + f.away_score) >= 3 THEN 1
                ELSE 0
            END,
            result_recorded_at = CURRENT_TIMESTAMP
        FROM fixtures f
        WHERE analyst_predictions.fixture_id = f.id
          AND analyst_predictions.is_backtest = 1
          AND f.home_score IS NOT NULL
          AND f.away_score IS NOT NULL
    """
    cur.execute(reconcile_sql)
    conn.commit()

    hits = conn.execute("""
        SELECT COUNT(*) FROM analyst_predictions
        WHERE is_backtest = 1 AND outcome_hit = 1
    """).fetchone()[0]
    total_recon = conn.execute("""
        SELECT COUNT(*) FROM analyst_predictions
        WHERE is_backtest = 1 AND outcome_hit IS NOT NULL
    """).fetchone()[0]
    print(f"   ✓ Reconciliados: {total_recon} partidos, {hits} acierto (acc={hits/max(1,total_recon)*100:.1f}%)")


if __name__ == "__main__":
    main()
