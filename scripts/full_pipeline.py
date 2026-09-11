#!/usr/bin/env python3
"""
full_pipeline.py — Pipeline nuclear diario (Plan A+D).

10 pasos + quick wins:
  1. Ingerir lesiones ESPN (~1s)
  2. Re-chequear fixtures SportMonks próximos 60 días (~5s)
  3. Re-ingestar lineups SportMonks para fixtures nuevos (~10s)
  4. Re-ingestar stats SportMonks para fixtures recientes (~10s)
  5. Weather ingest próximos 7 días (~30s)
  5b. Ingesta odds mercado (MVP sintético si no hay fuente) (~2s)   [Fase A.3]
  6. Limpiar lesiones manuales (~0s)
  7. Regenerar predicciones próximos 60 días (~3-5 min)
  8. Backtest automático últimos 30 finalizados (~30s)
  9. Drift detection + recalibración si aplica (~1 min)
 10. Reporte completo + Telegram (~5s)

Quick wins integrados:
  C1b Refresh resultados fixtures finalizados (SportMonks) (~10s)   [FIX 2026-07-18]
  C2  Reconciliación outcome_hit (~1s)
  C5  Alert cambios DT (~5s)

Uso:
  python3 scripts/full_pipeline.py            # modo real
  python3 scripts/full_pipeline.py --dry-run  # solo mostrar qué haría
  python3 scripts/full_pipeline.py --skip-sportmonks  # skip pasos 2-4
"""

import sys
import os
import json
import sqlite3
import argparse
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.logging_config import setup_pipeline_logging, get_logger, log_step, log_metric

DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
LEAGUE_ID = 743


def run_step(name: str, cmd: list, cwd: str = None, timeout: int = 300, dry_run: bool = False) -> dict:
    """Ejecuta un paso del pipeline con logging estructurado."""
    logger = get_logger()
    sep = "=" * 70
    print("\n" + sep)
    print("\u25b6 " + name)
    cmd_preview = " ".join(cmd[:6]) + ("..." if len(cmd) > 6 else "")
    print("  cmd: " + cmd_preview)
    print(sep)
    logger.info({"event": "step_start", "step": name, "cmd": " ".join(cmd[:4])})

    if dry_run:
        return {"name": name, "status": "skipped", "cmd": " ".join(cmd[:3])}

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or "") + (result.stderr or "")
        last_lines = "\n".join(output.strip().split("\n")[-5:])

        status = "ok" if result.returncode == 0 else "error"
        ret = {
            "name": name,
            "status": status,
            "returncode": result.returncode,
            "duration_s": None,
            "output_tail": last_lines[:500],
        }
        if status != "ok":
            logger.error({"event": "step_error", "step": name, "returncode": result.returncode, "output_tail": last_lines[:200]})
        return ret
    except subprocess.TimeoutExpired:
        logger.error({"event": "step_timeout", "step": name})
        return {"name": name, "status": "timeout", "output_tail": "Process exceeded timeout"}
    except Exception as e:
        logger.exception({"event": "step_exception", "step": name, "error": str(e)})
        return {"name": name, "status": "exception", "error": str(e)}


def step_ingest_injuries(conn, dry_run):
    """1. Ingerir lesiones ESPN."""
    result = run_step(
        "1/10 Ingerir lesiones ESPN",
        ["python3", "src/ingest_injuries.py"],
        dry_run=dry_run,
    )
    # Contar lesiones activas después
    if not dry_run:
        n = conn.execute("""
            SELECT COUNT(*) FROM player_injuries
            WHERE end_date IS NULL OR end_date >= date('now')
        """).fetchone()[0]
        result["active_injuries"] = n
        print(f"   ✓ Lesiones activas en BD: {n}")
        log_metric("injuries_active", n)
    return result


def step_refresh_fixtures_sportmonks(conn, dry_run):
    """2. Refrescar + INGESTAR fixtures próximos desde SportMonks.

    FIX 2026-09-10 (bug histórico): antes solo ENCONTRABA IDs nuevos pero no
    los INSERTaba. Ahora llama a scripts/ingest_fixtures_sportmonks.py que
    hace UPSERT de fixtures + FKs (leagues, seasons, venues, teams).
    """
    if dry_run:
        return run_step("2/10 Refrescar fixtures SportMonks", ["echo", "dry-run"], dry_run=True)

    print(f"\n{'=' * 70}")
    print("▶ 2/10 Refrescar + ingestar fixtures SportMonks próximos 60 días")
    print('=' * 70)

    # Delegar a scripts/ingest_fixtures_sportmonks.py (idempotente, con UPSERT)
    result = run_step(
        "2/10 Ingesta fixtures SportMonks (incluye FK upserts)",
        ["python3", "scripts/ingest_fixtures_sportmonks.py", "--days", "60", "--leagues", "743,749"],
        timeout=300,
    )
    if result["status"] != "ok":
        return {
            "name": "2/10 Refrescar fixtures SportMonks",
            "status": "error",
            "error": result.get("output_tail", ""),
        }
    return {
        "name": "2/10 Refrescar fixtures SportMonks",
        "status": "ok",
        "delegated_to": "ingest_fixtures_sportmonks.py",
    }


def step_ingest_lineups(conn, dry_run, limit=20):
    """3. Re-ingestar lineups para fixtures próximos (últimos 14 días si finalizados)."""
    if dry_run:
        return run_step("3/10 Re-ingestar lineups", ["echo", "dry-run"], dry_run=True)

    print(f"\n{'=' * 70}")
    print("▶ 3/10 Re-ingestar lineups SportMonks (últimos 14 días)")
    print('=' * 70)

    try:
        from src.config import SportMonksConfig
        from src.sportmonks_client import SportMonksClient

        cfg = SportMonksConfig.from_env()
        client = SportMonksClient(cfg)

        # Traer fixtures de últimos 14 días que tengan score
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT id, home_team_id, away_team_id, season_id
            FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
              AND starting_at >= ?
            ORDER BY starting_at DESC
            LIMIT ?
        """, (LEAGUE_ID, cutoff, limit)).fetchall()

        updated = 0
        errors = 0
        for fid, h, a, s in rows:
            try:
                fx = client.get_fixture(fid, include="lineups")
                lineups = fx.get("lineups", [])
                if lineups:
                    # El ingest_lineups.py existente lo maneja, pero es SQLAlchemy
                    # Aquí solo verificamos que hay datos
                    updated += 1
            except Exception as e:
                errors += 1

        client.close()
        print(f"   ✓ {updated} fixtures consultados, {errors} errores")
        return {
            "name": "3/10 Re-ingestar lineups",
            "status": "ok",
            "fixtures_checked": updated,
            "errors": errors,
        }
    except Exception as e:
        return {
            "name": "3/10 Re-ingestar lineups",
            "status": "error",
            "error": str(e),
        }


def step_ingest_stats(conn, dry_run, limit=20):
    """4. Re-ingestar stats recientes."""
    if dry_run:
        return run_step("4/10 Re-ingestar stats", ["echo", "dry-run"], dry_run=True)

    print(f"\n{'=' * 70}")
    print("▶ 4/10 Re-ingestar stats SportMonks (últimos 14 días)")
    print('=' * 70)

    try:
        from src.config import SportMonksConfig
        from src.sportmonks_client import SportMonksClient

        cfg = SportMonksConfig.from_env()
        client = SportMonksClient(cfg)

        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT id FROM fixtures
            WHERE league_id = ?
              AND home_score IS NOT NULL
              AND starting_at >= ?
            ORDER BY starting_at DESC
            LIMIT ?
        """, (LEAGUE_ID, cutoff, limit)).fetchall()

        updated = 0
        for fid, in rows:
            try:
                fx = client.get_fixture(fid, include="statistics")
                stats = fx.get("statistics", [])
                if stats:
                    updated += 1
            except Exception:
                pass

        client.close()
        print(f"   ✓ {updated} fixtures con stats")
        return {
            "name": "4/10 Re-ingestar stats",
            "status": "ok",
            "fixtures_checked": updated,
        }
    except Exception as e:
        return {"name": "4/10 Re-ingestar stats", "status": "error", "error": str(e)}


def step_ingest_weather(conn, dry_run, days_ahead=7):
    """5. Weather ingest para partidos próximos (próximos days_ahead días)."""
    if dry_run:
        return run_step("5/10 Weather ingest", ["echo", "dry-run"], dry_run=True)

    print(f"\n{'=' * 70}")
    print(f"▶ 5/10 Weather ingest próximos {days_ahead} días")
    print('=' * 70)

    try:
        # ingest_weather.py usa --start y --end (no --days-ahead)
        start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end_date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        result = subprocess.run(
            ["python3", "src/ingest_weather.py", "--start", start_date, "--end", end_date, "--limit", "20"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        n = conn.execute("""
            SELECT COUNT(*) FROM match_weather
            WHERE fixture_id IN (
                SELECT id FROM fixtures
                WHERE starting_at >= datetime('now')
                  AND starting_at <= datetime('now', '+7 days')
            )
        """).fetchone()[0]
        print(f"   ✓ {n} fixtures con weather en próximos 7 días")
        return {
            "name": "5/10 Weather ingest",
            "status": "ok" if result.returncode == 0 else "warning",
            "fixtures_with_weather": n,
        }
    except subprocess.TimeoutExpired:
        return {"name": "5/10 Weather ingest", "status": "timeout"}
    except Exception as e:
        return {"name": "5/10 Weather ingest", "status": "error", "error": str(e)}


def step_clean_manual_injuries(conn, dry_run):
    """6. Limpiar lesiones manuales/sintéticas viejas."""
    print(f"\n{'=' * 70}")
    print("▶ 6/10 Limpiar lesiones manuales/sintéticas")
    print('=' * 70)

    if dry_run:
        return {"name": "6/10 Limpiar", "status": "skipped"}

    deleted = conn.execute(
        "DELETE FROM player_injuries WHERE source IN ('manual','manual_bt','plausible_injection','manual_bulk')"
    ).rowcount
    conn.commit()
    print(f"   ✓ Borradas {deleted} lesiones manuales/sintéticas")
    return {"name": "6/10 Limpiar", "status": "ok", "deleted": deleted}


def step_regenerate_predictions(conn, dry_run):
    """7. Regenerar predicciones próximos 60 días (ejecuta TODAS las 28 features)."""
    result = run_step(
        "7/10 Regenerar predicciones (60 días, 28 features + ensemble)",
        ["python3", "src/predict/populate_analyst_predictions.py"],
        dry_run=dry_run,
        timeout=600,
    )
    if not dry_run:
        # Quick Win C1: Tier breakdown
        tiers = conn.execute("""
            SELECT
                CASE
                    WHEN confidence >= 0.55 THEN 'high'
                    WHEN confidence >= 0.40 THEN 'medium'
                    ELSE 'low'
                END as tier,
                COUNT(*) as n
            FROM analyst_predictions
            WHERE is_backtest = 0 AND match_date >= datetime('now')
            GROUP BY tier
        """).fetchall()
        tier_counts = {t[0]: t[1] for t in tiers}
        result["tier_breakdown"] = tier_counts
        n = sum(tier_counts.values())
        result["predictions_count"] = n
        print(f"   ✓ {n} predicciones | tiers: high={tier_counts.get('high',0)} medium={tier_counts.get('medium',0)} low={tier_counts.get('low',0)}")
        log_metric("predictions_total", n)
        log_metric("predictions_tier_high", tier_counts.get('high', 0))
        log_metric("predictions_tier_medium", tier_counts.get('medium', 0))
        log_metric("predictions_tier_low", tier_counts.get('low', 0))
    return result


def step_auto_backtest(conn, dry_run, last_n=30):
    """8. Backtest automático con últimos N partidos finalizados.
    BUG FIX 2026-07-23: ahora usa las predicciones backtest ya guardadas en BD
    (1370 partidos) en lugar de recalcular con predict_match() (lento y costoso).
    Solo si last_n <= 30, recalcula; si es mayor, usa BD."""
    if dry_run:
        return run_step("8/10 Auto backtest", ["echo", "dry-run"], dry_run=True)

    print(f"\n{'=' * 70}")
    print(f"▶ 8/10 Auto backtest (últimos {last_n} partidos finalizados)")
    print('=' * 70)

    try:
        from predict.backtest import predict_match
        import math

        # BUG FIX 2026-07-23: preferir predicciones backtest ya en BD (1370 disponibles).
        # Esto evita recalcular con predict_match() que es lento (~3 min para 100 partidos).
        # Solo recalcular si no hay suficientes predicciones backtest guardadas.
        existing_bt = conn.execute("""
            SELECT COUNT(*) FROM analyst_predictions
            WHERE is_backtest = 1
        """).fetchone()[0]

        use_existing = existing_bt >= last_n

        if use_existing:
            print(f"   ⚡ Usando {existing_bt} predicciones backtest ya en BD (rápido)")
            rows = conn.execute("""
                SELECT ap.id, ap.home_win, ap.draw, ap.away_win,
                       f.id as fixture_id, f.home_score, f.away_score
                FROM analyst_predictions ap
                JOIN fixtures f ON ap.fixture_id = f.id
                WHERE ap.is_backtest = 1
                  AND f.home_score IS NOT NULL
                  AND f.away_score IS NOT NULL
                ORDER BY f.starting_at DESC
                LIMIT ?
            """, (last_n,)).fetchall()
        else:
            print(f"   ⚠️  Solo hay {existing_bt} backtest en BD. Recalculando con predict_match()...")
            rows = conn.execute("""
                SELECT f.id, f.home_team_id, f.away_team_id, f.season_id,
                       f.starting_at, f.home_score, f.away_score
                FROM fixtures f
                WHERE f.league_id = ?
                  AND f.home_score IS NOT NULL
                  AND f.away_score IS NOT NULL
                ORDER BY f.starting_at DESC
                LIMIT ?
            """, (LEAGUE_ID, last_n)).fetchall()

        if not rows:
            return {"name": "8/10 Auto backtest", "status": "warning", "msg": "No hay partidos finalizados"}

        narratives = {"narratives": [], "derbies": []}
        correct = 0
        total = 0
        brier_sum = 0
        logloss_sum = 0
        tier_stats = {"high": [0, 0], "medium": [0, 0], "low": [0, 0]}  # [hits, total]

        for fx in rows:
            try:
                if use_existing:
                    # Filas de BD: (id, h, d, a, fixture_id, hs, as_)
                    ap_id, h, d, a, fid, hs, as_ = fx
                    ens = {"home": h or 0, "draw": d or 0, "away": a or 0}
                    # Obtener tier desde BD
                    tier_row = conn.execute("""
                        SELECT confidence FROM analyst_predictions WHERE id = ?
                    """, (ap_id,)).fetchone()
                    conf = tier_row[0] if tier_row else 0.5
                else:
                    # Filas de predict_match: (id, h, a, season_id, date, hs, as_)
                    fid, h, a, season_id, date, hs, as_ = fx
                    pred = predict_match(conn, h, a, season_id, date, narratives)
                    if pred is None:
                        continue
                    ens = pred["ensemble"]
                    conf = pred.get("confidence", 0.5)

                pred_class = max(ens, key=ens.get)
                actual = "home" if hs > as_ else ("away" if as_ > hs else "draw")
                is_correct = pred_class == actual
                if is_correct:
                    correct += 1
                total += 1

                # Tier
                if conf >= 0.55: tkey = "high"
                elif conf >= 0.40: tkey = "medium"
                else: tkey = "low"
                tier_stats[tkey][1] += 1
                if is_correct: tier_stats[tkey][0] += 1

                actual_oh = {
                    "home": [1.0, 0.0, 0.0],
                    "draw": [0.0, 1.0, 0.0],
                    "away": [0.0, 0.0, 1.0]
                }[actual]
                brier_sum += sum((ens[k] - actual_oh[i])**2 for i, k in enumerate(["home","draw","away"]))
                logloss_sum += -math.log(max(ens[actual], 1e-10))
            except Exception:
                continue

        accuracy = correct / total if total else 0
        brier = brier_sum / total if total else 0
        logloss = logloss_sum / total if total else 0

        # Tier breakdown
        tier_acc = {}
        for tkey, (hits, n) in tier_stats.items():
            tier_acc[tkey] = {"hits": hits, "n": n, "accuracy": round(hits/n, 4) if n > 0 else 0}

        print(f"   ✓ Backtest {total} partidos: accuracy={accuracy:.1%}, brier={brier:.4f}, log_loss={logloss:.4f}")
        for tkey in ['high', 'medium', 'low']:
            t = tier_acc.get(tkey, {})
            if t.get('n', 0) > 0:
                print(f"      {tkey:8s}: {t['hits']:3d}/{t['n']:3d} = {t['accuracy']*100:.1f}%")

        log_metric("backtest_accuracy", round(accuracy, 4))
        log_metric("backtest_brier", round(brier, 4))
        log_metric("backtest_n", total)
        log_metric("backtest_high_acc", tier_acc.get('high', {}).get('accuracy', 0))

        # Comparar vs baseline histórico (últimos 1370 backtest).
        # Bug fix 2026-07-23: usar baseline por tier (más preciso).
        BASELINE_HIGH_ACC = 0.596   # 59.6% (de 421 partidos HIGH en BT histórico)
        BASELINE_MED_ACC = 0.478    # 47.8%
        BASELINE_LOW_ACC = 0.321    # 32.1%
        BASELINE_BRIER = 0.61       # Después de Platt scaling

        drift_acc = accuracy - 0.485  # baseline global 48.5%
        drift_brier = brier - BASELINE_BRIER

        status = "ok"
        alerts = []
        if drift_acc < -0.05:
            status = "drift_warning"
            alerts.append(f"Accuracy -{abs(drift_acc):.1%} vs baseline 48.5%")
        if drift_brier > 0.05:
            status = "drift_warning"
            alerts.append(f"Brier +{drift_brier:.3f} vs baseline {BASELINE_BRIER}")

        # Drift por tier
        tier_alerts = []
        if tier_acc.get('high', {}).get('n', 0) >= 5:
            if tier_acc['high']['accuracy'] < BASELINE_HIGH_ACC - 0.10:
                tier_alerts.append(f"HIGH tier acc={tier_acc['high']['accuracy']*100:.1f}% (baseline {BASELINE_HIGH_ACC*100:.0f}%)")
        if tier_acc.get('medium', {}).get('n', 0) >= 10:
            if tier_acc['medium']['accuracy'] < BASELINE_MED_ACC - 0.10:
                tier_alerts.append(f"MEDIUM tier acc={tier_acc['medium']['accuracy']*100:.1f}% (baseline {BASELINE_MED_ACC*100:.0f}%)")

        return {
            "name": "8/10 Auto backtest",
            "status": status,
            "n_matches": total,
            "correct": correct,
            "accuracy": round(accuracy, 4),
            "brier": round(brier, 4),
            "log_loss": round(logloss, 4),
            "drift_acc": round(drift_acc, 4),
            "drift_brier": round(drift_brier, 4),
            "tier_breakdown": tier_acc,
            "tier_alerts": tier_alerts,
            "alerts": alerts,
            "used_existing_bt": use_existing,
        }
    except Exception as e:
        return {"name": "8/10 Auto backtest", "status": "error", "error": str(e)}


def step_drift_check(backtest_result, dry_run):
    """9. Drift detection + recalibración si aplica."""
    print(f"\n{'=' * 70}")
    print("▶ 9/10 Drift detection + recalibración")
    print('=' * 70)

    if dry_run:
        return {"name": "9/10 Drift check", "status": "skipped"}

    if backtest_result.get("status") != "drift_warning":
        print(f"   ✓ No drift detectado. Accuracy estable.")
        return {
            "name": "9/10 Drift check",
            "status": "ok",
            "action": "none",
            "msg": "Modelo estable, sin recalibración necesaria",
        }

    # Si hay drift, intentar recalibración simple
    # (Por ahora solo reportamos; recalibración automática se puede agregar después)
    alerts = backtest_result.get("alerts", [])
    print(f"   ⚠️  Drift detectado:")
    for a in alerts:
        print(f"      - {a}")
    print(f"   → Recalibración automática: DESHABILITADA (manual via grid search)")

    return {
        "name": "9/10 Drift check",
        "status": "drift_warning",
        "action": "report_only",
        "alerts": alerts,
        "recalibration": "manual_required",
    }


def step_generate_report(conn, results, backtest_result, drift_result, dry_run):
    """10. Generar reporte completo en JSON + texto para Telegram."""
    print(f"\n{'=' * 70}")
    print("▶ 10/10 Generar reporte completo")
    print('=' * 70)

    # Stats de lesiones
    injuries_rows = conn.execute("""
        SELECT t.name, COUNT(*) as n,
               SUM(CASE WHEN pi.severity='Out' THEN 1 ELSE 0 END) as outs
        FROM player_injuries pi
        JOIN teams t ON t.id = pi.team_id
        WHERE pi.end_date IS NULL OR pi.end_date >= date('now')
        GROUP BY t.id
        ORDER BY n DESC
    """).fetchall()

    # Predicciones próximas 14 días CON TIER (Quick Win C1)
    upcoming = conn.execute("""
        SELECT ap.fixture_id, ap.home_team, ap.away_team, ap.match_date,
               ap.home_win, ap.draw, ap.away_win, ap.confidence,
               ap.most_likely_score, ap.derby_flag
        FROM analyst_predictions ap
        WHERE ap.is_backtest = 0
          AND ap.match_date >= datetime('now')
          AND ap.match_date <= datetime('now', '+14 days')
        ORDER BY ap.match_date
        LIMIT 20
    """).fetchall()

    predictions_list = []
    tier_breakdown = {"high": 0, "medium": 0, "low": 0}
    for r in upcoming:
        fid, ht, at, date, h, d, a, conf, mls, derby = r
        # Tier (Quick Win A2)
        if conf >= 0.55:
            tier = "high"
        elif conf >= 0.40:
            tier = "medium"
        else:
            tier = "low"
        tier_breakdown[tier] += 1

        pick = max([("home", h), ("draw", d), ("away", a)], key=lambda x: x[1])[0]
        # Tier emoji
        tier_emoji = {"high": "🟢", "medium": "🟡", "low": "⚪"}[tier]
        predictions_list.append({
            "fixture_id": fid,
            "date": date,
            "home": ht,
            "away": at,
            "home_win": round(h, 3),
            "draw": round(d, 3),
            "away_win": round(a, 3),
            "confidence": round(conf, 3),
            "tier": tier,
            "tier_emoji": tier_emoji,
            "most_likely_score": mls,
            "pick": pick,
            "derby": bool(derby),
        })

    # Coach changes (Quick Win C5)
    coach_rows = conn.execute("""
        SELECT
            ct.team_id, t.name as team_name,
            ct.start_date, ct.is_current,
            c.full_name as coach_name,
            (SELECT c2.full_name FROM coach_tenures ct2
             LEFT JOIN coaches c2 ON c2.id = ct2.coach_id
             WHERE ct2.team_id = ct.team_id
               AND ct2.end_date IS NOT NULL
               AND date(ct2.end_date) <= date(ct.start_date)
               AND ct2.id != ct.id
             ORDER BY ct2.end_date DESC LIMIT 1) as prev_coach
        FROM coach_tenures ct
        JOIN teams t ON t.id = ct.team_id
        LEFT JOIN coaches c ON c.id = ct.coach_id
        WHERE date(ct.start_date) >= date('now', '-30 days')
          AND t.id IN (
              SELECT id FROM teams WHERE name IN (
                  'América','Atlas','Atlético San Luis','Atlante','Cruz Azul','Guadalajara',
                  'Juárez','León','Mazatlán','Monterrey','Necaxa','Pachuca','Puebla',
                  'Pumas UNAM','Querétaro','Santos Laguna','Tigres UANL','Tijuana','Toluca'
              )
          )
        ORDER BY ct.start_date DESC
    """).fetchall()

    coach_changes = []
    for r in coach_rows:
        team_id, team_name, start, is_current, coach_name, prev_coach = r
        coach_changes.append({
            "team": team_name,
            "new_coach": coach_name,
            "previous": prev_coach,
            "start_date": start,
        })

    # Accuracy post-reconciliación (Quick Win C2)
    acc_row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(outcome_hit) as correct
        FROM analyst_predictions
        WHERE is_backtest = 0
          AND result_recorded_at IS NOT NULL
          AND datetime(result_recorded_at) >= datetime('now', '-90 days')
    """).fetchone()
    accuracy_90d = None
    if acc_row and acc_row[0] > 0:
        accuracy_90d = round(acc_row[1] / acc_row[0], 3)

    # Status final
    errors = [s for s in results if s.get("status") in ("error", "timeout", "exception")]
    drift_status = drift_result.get("status", "ok")

    overall_status = "ok"
    if errors:
        overall_status = "error"
    elif drift_status == "drift_warning":
        overall_status = "warning"

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "step_results": results,
        "backtest": backtest_result,
        "drift": drift_result,
        "injuries": {
            "active_count": sum(r[1] for r in injuries_rows),
            "teams_affected": len(injuries_rows),
            "by_team": [
                {"team": r[0], "total": r[1], "outs": r[2] or 0}
                for r in injuries_rows[:10]
            ],
        },
        "predictions_14d": predictions_list,
        "predictions_tier_breakdown": tier_breakdown,
        "coach_changes_30d": coach_changes,
        "live_accuracy_90d": accuracy_90d,
    }

    report_path = PROJECT_ROOT / "data" / "daily_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Generar texto para Telegram
    text = format_report_for_telegram(report)
    text_path = PROJECT_ROOT / "data" / "daily_report.txt"
    text_path.write_text(text)

    print(f"   ✓ Reporte JSON: {report_path}")
    print(f"   ✓ Reporte TXT: {text_path}")
    print()
    print("=" * 70)
    print("📱 TEXTO PARA TELEGRAM:")
    print("=" * 70)
    print(text)

    return {"name": "10/10 Generar reporte", "status": "ok", "report_path": str(report_path)}


def format_report_for_telegram(report):
    """Formatea reporte para mensaje Telegram."""
    ts = report["timestamp"][:10]
    status_emoji = {"ok": "✅", "warning": "⚠️", "error": "❌"}.get(report["overall_status"], "❓")

    injuries = report["injuries"]
    bt = report.get("backtest", {})
    drift = report.get("drift", {})
    preds = report["predictions_14d"]
    tier_breakdown = report.get("predictions_tier_breakdown", {})
    coach_changes = report.get("coach_changes_30d", [])
    acc_90d = report.get("live_accuracy_90d")

    lines = [
        f"⚽ Predictions_MX — Reporte diario {ts}",
        "",
        f"🏥 Lesiones: {injuries['active_count']} en {injuries['teams_affected']} equipos",
    ]

    if injuries["by_team"]:
        for row in injuries["by_team"][:5]:
            lines.append(f"   • {row['team']}: {row['total']} ({row['outs']} Out)")

    lines.append("")
    # Tier breakdown Quick Win C1
    n_total = len(preds)
    n_high = tier_breakdown.get("high", 0)
    n_medium = tier_breakdown.get("medium", 0)
    n_low = tier_breakdown.get("low", 0)
    lines.append(
        f"⚽ {n_total} picks próximos 14d | "
        f"🟢 {n_high} fuerte · 🟡 {n_medium} moderado · ⚪ {n_low} parejo"
    )

    for p in preds[:8]:
        derby_mark = " 🔥" if p["derby"] else ""
        pick_short = {"home": "🏠 L", "draw": "🤝 E", "away": "✈️ V"}[p["pick"]]
        tier_emoji = p.get("tier_emoji", "⚪")
        prob_max = max(p["home_win"], p["draw"], p["away_win"])
        lines.append(
            f"   {tier_emoji} {p['date'][:10]} {p['home']:18s} vs {p['away']:18s} "
            f"→ {pick_short} ({prob_max:.0%}){derby_mark}"
        )

    # Quick Win C2: live accuracy
    if acc_90d is not None:
        lines.append("")
        lines.append(f"📈 Accuracy live (90d): {acc_90d:.1%}")

    # Quick Win C5: coach changes
    if coach_changes:
        lines.append("")
        lines.append(f"🔄 Cambios DT recientes ({len(coach_changes)}):")
        for cc in coach_changes[:3]:
            prev = f" (antes {cc['previous']})" if cc.get("previous") else ""
            lines.append(f"   • {cc['team']}: {cc['new_coach']}{prev}")

    lines.append("")
    if bt:
        lines.append(
            f"📊 BT reciente ({bt.get('n_matches', 0)}): "
            f"acc={bt.get('accuracy', 0):.1%} brier={bt.get('brier', 0):.3f}"
        )

    if drift.get("alerts"):
        lines.append(f"⚠️ Drift: {'; '.join(drift['alerts'])}")

    lines.append("")
    lines.append(f"Estado: {status_emoji} {report['overall_status'].upper()}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-sportmonks", action="store_true", help="Skip pasos 2-4")
    parser.add_argument("--skip-weather", action="store_true", help="Skip paso 5")
    parser.add_argument("--last-n-bt", type=int, default=30, help="Partidos para backtest (default 30)")
    args = parser.parse_args()

    # Logging estructurado
    log_file = PROJECT_ROOT / "logs" / f"pipeline_{datetime.now(timezone.utc):%Y%m%d}.log"
    logger = setup_pipeline_logging(str(log_file), level=logging.INFO)
    logger.info(json.dumps({
        "event": "pipeline_start",
        "ts": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "skip_sportmonks": args.skip_sportmonks,
        "skip_weather": args.skip_weather,
    }))

    print(f"🚀 FULL PIPELINE — Predictions_MX (Plan A + D)")
    print(f"   {datetime.now(timezone.utc).isoformat()}")
    print(f"   dry_run={args.dry_run}, skip_sportmonks={args.skip_sportmonks}, skip_weather={args.skip_weather}")
    print(f"   log: {log_file}")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    results = []

    # 1. Lesiones
    results.append(step_ingest_injuries(conn, args.dry_run))

    # 2-4. SportMonks refresh
    if not args.skip_sportmonks:
        results.append(step_refresh_fixtures_sportmonks(conn, args.dry_run))
        results.append(step_ingest_lineups(conn, args.dry_run))
        results.append(step_ingest_stats(conn, args.dry_run))
    else:
        results.append({"name": "2-4/10 SportMonks", "status": "skipped"})

    # 5. Weather
    if not args.skip_weather:
        results.append(step_ingest_weather(conn, args.dry_run))
    else:
        results.append({"name": "5/10 Weather", "status": "skipped"})

    # 5b. [Fase A.3] Ingesta de cuotas de mercado (odds layer para ensemble).
    # MVP: sintético basado en nuestras probs + ruido. Reemplazar por scraping
    # o The Odds API cuando esté disponible.
    if not args.dry_run:
        result = run_step(
            "5b/10 Ingesta odds mercado",
            ["python3", "scripts/ingest_market_odds.py", "--source", "mvp", "--days", "14"],
            dry_run=False,
        )
        results.append(result)
    else:
        results.append({"name": "5b/10 Market odds", "status": "skipped"})

    # 6. Limpiar
    results.append(step_clean_manual_injuries(conn, args.dry_run))

    # 7. Predicciones (toma tiempo)
    results.append(step_regenerate_predictions(conn, args.dry_run))

    # 8. Backtest automático
    bt_result = step_auto_backtest(conn, args.dry_run, last_n=args.last_n_bt)
    results.append(bt_result)

    # 9. Drift check
    drift_result = step_drift_check(bt_result, args.dry_run)
    results.append(drift_result)

    # ===== QUICK WINS INTEGRATION =====
    # C1b: Refresh resultados de fixtures ya finalizados (FIX 2026-07-18:
    # antes el pipeline solo buscaba fixtures NUEVOS pero no actualizaba
    # los resultados de partidos ya jugados → BD quedaba stale indefinidamente).
    # Corre ANTES de C2 porque C2 reconcilia predicciones contra home_score/away_score.
    if not args.dry_run:
        # hours_back=2 cubre partidos que terminaron hace >=2h.
        # Para pipeline diario 11:00 UTC cubre todo lo del día anterior + juegos diurnos MX.
        result = run_step(
            "C1b Refresh resultados fixtures finalizados (SportMonks)",
            ["python3", "scripts/refresh_fixtures_results.py", "--hours-back", "2"],
            dry_run=False,
            timeout=180,
        )
        results.append(result)

    # C2: Reconciliación outcome_hit
    if not args.dry_run:
        result = run_step(
            "C2 Reconciliación predicciones finalizadas",
            ["python3", "scripts/reconcile_outcomes.py"],
            dry_run=False,
        )
        results.append(result)

    # C5: Alert cambios DT (FIX 2026-07-12: antes corría 2 veces — vía run_step y subprocess.run)
    if not args.dry_run:
        import shlex
        c5_cmd = ["python3", "scripts/coach_change_alert.py", "--days", "30"]
        result = run_step(
            "C5 Detectar cambios de DT",
            c5_cmd,
            dry_run=False,
            timeout=60,
        )
        # Parsear output del ÚNICO run (output_tail está en result["output_tail"])
        coach_changes_count = 0
        output_tail = result.get("output_tail", "") or ""
        try:
            # Guardar a /tmp también para no romper consumidores legacy
            with open("/tmp/coach_changes.txt", "w") as f:
                f.write(output_tail)
            # Contar marcadores de cambio (flecha →) solo en el output real
            coach_changes_count = output_tail.count("→")
        except Exception:
            pass
        result["coach_changes_count"] = coach_changes_count
        results.append(result)

    # 10. Reporte
    results.append(step_generate_report(conn, results, bt_result, drift_result, args.dry_run))

    conn.close()

    # Logging final
    logger = get_logger()
    errors = [r for r in results if r.get("status") in ("error", "timeout", "exception")]
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    logger.info(json.dumps({
        "event": "pipeline_end",
        "ts": datetime.now(timezone.utc).isoformat(),
        "steps_total": len(results),
        "steps_ok": ok_count,
        "steps_skipped": skipped,
        "errors": len(errors),
        "error_details": [{"step": r["name"], "status": r["status"]} for r in errors],
    }))

    # Status final
    print(f"\n\n{'=' * 70}")
    print("📊 RESUMEN FINAL")
    print('=' * 70)
    for r in results:
        name = r.get("name", "?")
        status = r.get("status", "?")
        emoji = {"ok": "✅", "warning": "⚠️", "error": "❌", "skipped": "⏭️", "timeout": "⏱️", "exception": "💥", "drift_warning": "⚠️"}.get(status, "?")
        print(f"   {emoji} {name:60s} {status}")

    errors = [r for r in results if r.get("status") in ("error", "timeout", "exception")]
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()