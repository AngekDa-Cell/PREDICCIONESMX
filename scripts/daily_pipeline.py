#!/usr/bin/env python3
"""
daily_pipeline.py — Flujo diario automatizado.

Pasos:
  1. Ingerir lesiones ESPN API
  2. Regenerar predicciones para partidos próximos (próximos 60 días)
  3. Limpiar lesiones manuales/sintéticas viejas
  4. Reportar resumen

Pensado para correr vía cron diario.

Uso:
  python3 scripts/daily_pipeline.py            # modo real
  python3 scripts/daily_pipeline.py --dry-run  # solo mostrar qué haría
"""

import sys
import json
import sqlite3
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


def run_step(name: str, cmd: list, dry_run: bool = False) -> dict:
    """Ejecuta un paso del pipeline."""
    print(f"\n{'=' * 60}")
    print(f"▶ {name}")
    print(f"  cmd: {' '.join(cmd)}")
    print('=' * 60)

    if dry_run:
        return {"name": name, "status": "skipped", "cmd": ' '.join(cmd)}

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max
        )
        output = (result.stdout or "") + (result.stderr or "")
        last_lines = '\n'.join(output.strip().split('\n')[-10:])

        return {
            "name": name,
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "output_tail": last_lines,
        }
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "timeout", "output_tail": "Process exceeded 5 min"}
    except Exception as e:
        return {"name": name, "status": "exception", "error": str(e)}


def get_upcoming_predictions(conn) -> list:
    """Devuelve las predicciones de partidos próximos (no BT)."""
    rows = conn.execute("""
        SELECT ap.fixture_id, ap.home_team, ap.away_team, ap.match_date,
               ap.home_win, ap.draw, ap.away_win, ap.confidence,
               ap.most_likely_score, ap.derby_flag
        FROM analyst_predictions ap
        WHERE ap.is_backtest = 0
          AND ap.match_date >= datetime('now')
          AND ap.match_date <= datetime('now', '+14 days')
        ORDER BY ap.match_date
    """).fetchall()
    return rows


def get_injury_summary(conn) -> dict:
    """Resumen de lesiones activas por equipo."""
    rows = conn.execute("""
        SELECT t.name, COUNT(*) as n,
               SUM(CASE WHEN pi.severity='Out' THEN 1 ELSE 0 END) as outs,
               SUM(CASE WHEN pi.severity='Doubtful' THEN 1 ELSE 0 END) as doubt
        FROM player_injuries pi
        JOIN teams t ON t.id = pi.team_id
        WHERE pi.end_date IS NULL OR pi.end_date >= date('now')
        GROUP BY t.id
        ORDER BY n DESC
    """).fetchall()
    return {
        "teams_with_injuries": len(rows),
        "total_teams_affected": sum(1 for r in rows if r[1] > 0),
        "by_team": [{"team": r[0], "total": r[1], "outs": r[2], "doubtful": r[3]} for r in rows],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-injuries", action="store_true",
                        help="Saltar ingesta de lesiones")
    parser.add_argument("--skip-predictions", action="store_true",
                        help="Saltar regeneración de predicciones")
    args = parser.parse_args()

    print(f"🔄 DAILY PIPELINE — Predictions_MX")
    print(f"   {datetime.now(timezone.utc).isoformat()}")
    print(f"   dry_run={args.dry_run}")

    results = []

    # ── Paso 1: Ingerir lesiones ──
    if not args.skip_injuries:
        results.append(run_step(
            "1/3 Ingerir lesiones ESPN",
            ["python3", "src/ingest_injuries.py"],
            dry_run=args.dry_run,
        ))

    # ── Paso 2: Limpiar lesiones manuales/sintéticas viejas ──
    if not args.dry_run:
        print(f"\n{'=' * 60}")
        print("▶ 2/3 Limpiar lesiones manuales/sintéticas")
        print('=' * 60)
        conn = sqlite3.connect(str(DB_PATH))
        deleted = conn.execute(
            "DELETE FROM player_injuries WHERE source IN ('manual','manual_bt','plausible_injection','manual_bulk')"
        ).rowcount
        conn.commit()
        conn.close()
        print(f"   Borradas {deleted} lesiones manuales/sintéticas")
        results.append({"name": "2/3 Limpiar", "status": "ok", "deleted": deleted})

    # ── Paso 3: Regenerar predicciones para partidos próximos ──
    if not args.skip_predictions:
        results.append(run_step(
            "3/3 Regenerar predicciones (próximos 60 días)",
            ["python3", "src/predict/populate_analyst_predictions.py"],
            dry_run=args.dry_run,
        ))

    # ── Resumen ──
    print(f"\n\n{'=' * 60}")
    print("📊 RESUMEN DEL DÍA")
    print('=' * 60)

    conn = sqlite3.connect(str(DB_PATH))

    injuries_summary = get_injury_summary(conn)
    upcoming = get_upcoming_predictions(conn)

    print(f"\n🏥 Lesiones activas: {injuries_summary['total_teams_affected']} equipos afectados")
    if injuries_summary['by_team']:
        for row in injuries_summary['by_team'][:8]:
            print(f"   {row['team']:25s} total={row['total']:>2}  Out={row['outs']:>2}  Doubtful={row['doubtful']:>2}")

    print(f"\n⚽ Predicciones activas (próximos 14 días): {len(upcoming)}")
    for row in upcoming[:10]:
        fid, ht, at, date, h, d, a, conf, mls, derby = row
        pick = max([("home", h), ("draw", d), ("away", a)], key=lambda x: x[1])
        derby_mark = " 🔥" if derby else ""
        print(f"   {date[:16]} {ht:20s} vs {at:20s} → {pick[0].upper():5s} ({pick[1]:.1%}){derby_mark}")

    conn.close()

    # ── Output JSON para delivery ──
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": results,
        "injuries_summary": injuries_summary,
        "upcoming_predictions_count": len(upcoming),
        "upcoming_predictions": [
            {
                "fixture_id": r[0],
                "home": r[1],
                "away": r[2],
                "date": r[3],
                "home_win": round(r[4], 3),
                "draw": round(r[5], 3),
                "away_win": round(r[6], 3),
                "confidence": round(r[7], 3),
                "most_likely_score": r[8],
                "derby": bool(r[9]),
                "pick": max([("home", r[4]), ("draw", r[5]), ("away", r[6])], key=lambda x: x[1])[0],
            }
            for r in upcoming[:15]
        ],
    }

    report_path = PROJECT_ROOT / "data" / "daily_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n📄 Reporte guardado en {report_path}")

    # Status final
    errors = [s for s in results if s.get("status") not in ("ok", "skipped")]
    if errors:
        print(f"\n❌ Errores: {len(errors)}")
        for e in errors:
            print(f"   {e.get('name')}: {e.get('status')} {e.get('error', '')}")
        sys.exit(1)
    else:
        print("\n✅ Pipeline completado sin errores")


if __name__ == "__main__":
    main()