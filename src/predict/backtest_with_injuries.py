#!/usr/bin/env python3
"""
backtest_with_injuries.py — BT A/B para validar feature de lesiones.

Compara accuracy del ensemble:
  - Baseline: sin lesiones
  - Treatment: con lesiones inyectadas plausibles

Output: accuracy, brier, log_loss para ambos.
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"


def get_bt_fixtures(conn):
    """Devuelve los 14 partidos BT del modelo (resultados desde fixtures)."""
    rows = conn.execute("""
        SELECT ap.fixture_id, f.home_team_id, f.away_team_id, f.season_id,
               f.starting_at, f.home_score, f.away_score,
               ap.home_team, ap.away_team
        FROM analyst_predictions ap
        JOIN fixtures f ON f.id = ap.fixture_id
        WHERE ap.is_backtest = 1
          AND f.home_score IS NOT NULL
          AND f.away_score IS NOT NULL
        ORDER BY f.starting_at
    """).fetchall()
    return rows


def get_team_key_players(conn, team_id, season_id, before_date, n=5):
    """
    Devuelve los N jugadores más importantes del equipo (titulares habituales).
    Usa is_starter como proxy si minutes_played es NULL.
    """
    rows = conn.execute("""
        SELECT p.id, p.full_name, p.primary_position, p.secondary_position,
               SUM(CASE WHEN fl.is_starter=1 THEN 1 ELSE 0 END) as starts,
               COUNT(*) as games,
               SUM(fl.goals) as total_goals,
               SUM(fl.assists) as total_assists
        FROM fixture_lineups fl
        JOIN players p ON p.id = fl.player_id
        JOIN fixtures f ON f.id = fl.fixture_id
        WHERE fl.team_id = ?
          AND f.season_id = ?
          AND f.starting_at < ?
        GROUP BY p.id
        HAVING games >= 3 AND starts >= 2
        ORDER BY starts DESC, total_goals DESC, total_assists DESC
        LIMIT ?
    """, (team_id, season_id, before_date, n)).fetchall()
    return rows


def inject_plausible_injuries(conn, fixtures, rng_seed=42):
    """
    Inyecta lesiones plausibles para los BT:
    - 30% de equipos tienen 1 Out
    - 10% de equipos tienen 1 Doubtful
    - Solo jugadores titulares importantes
    """
    import random
    rng = random.Random(rng_seed)

    injuries_added = []
    for fx in fixtures:
        fid, home_id, away_id, season_id, date, hs, as_, ht, at = fx
        for team_id, team_name in [(home_id, ht), (away_id, at)]:
            roll = rng.random()
            if roll < 0.30:
                # 1 Out en este equipo
                players = get_team_key_players(conn, team_id, season_id, date, n=5)
                if players:
                    player = rng.choice(players)
                    start = (datetime.fromisoformat(date.replace("Z", "").replace("T", " ").split(".")[0])
                             - timedelta(days=rng.randint(3, 10))).strftime("%Y-%m-%d")
                    end = (datetime.fromisoformat(date.replace("Z", "").replace("T", " ").split(".")[0])
                           + timedelta(days=rng.randint(14, 30))).strftime("%Y-%m-%d")
                    meta = json.dumps({
                        "source": "plausible_injection",
                        "display_name": player[1],
                        "position": player[2] or player[3] or "",
                    })
                    injuries_added.append((player[0], team_id, season_id, start, end,
                                           "Lesión", "Out", "manual_bt", meta, team_name, player[1]))
            elif roll < 0.40:
                # 1 Doubtful
                players = get_team_key_players(conn, team_id, season_id, date, n=5)
                if players:
                    player = rng.choice(players)
                    start = (datetime.fromisoformat(date.replace("Z", "").replace("T", " ").split(".")[0])
                             - timedelta(days=rng.randint(1, 3))).strftime("%Y-%m-%d")
                    end = (datetime.fromisoformat(date.replace("Z", "").replace("T", " ").split(".")[0])
                           + timedelta(days=rng.randint(3, 10))).strftime("%Y-%m-%d")
                    meta = json.dumps({
                        "source": "plausible_injection",
                        "display_name": player[1],
                        "position": player[2] or player[3] or "",
                    })
                    injuries_added.append((player[0], team_id, season_id, start, end,
                                           "Molestia", "Doubtful", "manual_bt", meta, team_name, player[1]))

    return injuries_added


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--injury-weight", type=float, default=0.05,
                        help="Peso del boost por lesiones (default 0.05)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))

    fixtures = get_bt_fixtures(conn)
    print(f"📊 BT A/B — {len(fixtures)} partidos")
    print(f"   Injury weight = {args.injury_weight}")
    print()

    # Limpiar lesiones previas de BT
    conn.execute("DELETE FROM player_injuries WHERE source = 'manual_bt'")
    conn.commit()

    # ── PASO 1: Baseline SIN lesiones ──
    print("=" * 60)
    print("🅰️  BASELINE (sin lesiones)")
    print("=" * 60)
    baseline = run_mini_backtest(conn, fixtures, injury_weight=0.0)

    # ── PASO 2: Treatment CON lesiones plausibles ──
    print()
    print("=" * 60)
    print("🅱️  TREATMENT (con lesiones plausibles)")
    print("=" * 60)
    injuries = inject_plausible_injuries(conn, fixtures, rng_seed=42)
    for inj in injuries:
        pid, tid, sid, start, end, itype, sev, src, meta, team, player = inj
        conn.execute("""
            INSERT INTO player_injuries
            (player_id, team_id, season_id, start_date, end_date,
             injury_type, severity, source, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (pid, tid, sid, start, end, itype, sev, src, meta))
    conn.commit()
    print(f"💉 Inyectadas {len(injuries)} lesiones plausibles")
    for inj in injuries[:10]:
        print(f"   {inj[9]:20s} {inj[10][:25]:25s} {inj[6]:12s}")

    treatment = run_mini_backtest(conn, fixtures, injury_weight=args.injury_weight)

    # ── PASO 3: Comparar ──
    print()
    print("=" * 60)
    print("📈 COMPARATIVA")
    print("=" * 60)
    print(f"{'Métrica':<20} {'Baseline':>12} {'Treatment':>12} {'Δ':>10}")
    print("-" * 60)
    for k in ["accuracy", "brier", "log_loss", "correct"]:
        b = baseline[k]
        t = treatment[k]
        if k == "accuracy":
            print(f"{k:<20} {b:>12.3f} {t:>12.3f} {t-b:>+10.3f}")
        elif k in ["brier", "log_loss"]:
            print(f"{k:<20} {b:>12.4f} {t:>12.4f} {t-b:>+10.4f}")
        else:
            print(f"{k:<20} {b:>12} {t:>12} {t-b:>+10}")

    # Limpiar
    conn.execute("DELETE FROM player_injuries WHERE source = 'manual_bt'")
    conn.commit()
    conn.close()


def run_mini_backtest(conn, fixtures, injury_weight):
    """
    Corre BT mini sobre los fixtures dados con un injury_weight dado.
    Inyecta el weight al módulo antes de correr.
    """
    from predict import backtest as bt_mod

    # Override INJURY_WEIGHT
    orig_predict = bt_mod.predict_match

    def predict_with_weight(conn_, h_, a_, s_, d_, narratives):
        # Patch INJURY_WEIGHT dinámicamente
        import predict.features as feat_mod
        # Llamar con weight custom: parcheamos antes
        result = orig_predict(conn_, h_, a_, s_, d_, narratives)
        # Si quisiéramos override, recalculamos. Aquí aceptamos que el weight
        # ya está fijo en el código. Para experimento: reimportamos con patch.
        return result

    # Recargar módulo con weight custom
    import importlib
    importlib.reload(bt_mod)

    # Monkey-patch: override la constante INJURY_WEIGHT antes de que predict_match se llame
    bt_mod.INJURY_WEIGHT = injury_weight

    correct = 0
    total = 0
    brier_sum = 0
    logloss_sum = 0

    narratives = {"narratives": [], "derbies": []}

    for fx in fixtures:
        fid, home_id, away_id, season_id, date, hs, as_, ht, at = fx
        try:
            pred = bt_mod.predict_match(conn, home_id, away_id, season_id, date, narratives)
            if pred is None:
                continue

            ens = pred["ensemble"]
            pred_class = max(ens, key=ens.get)

            if hs > as_:
                actual = "home"
            elif as_ > hs:
                actual = "away"
            else:
                actual = "draw"

            if pred_class == actual:
                correct += 1
            total += 1

            # Brier
            actual_oh = {"home": 1.0, "draw": 0.0, "away": 0.0} if actual == "home" else \
                        {"home": 0.0, "draw": 1.0, "away": 0.0} if actual == "draw" else \
                        {"home": 0.0, "draw": 0.0, "away": 1.0}
            brier = sum((ens[k] - actual_oh[k]) ** 2 for k in ["home", "draw", "away"])
            brier_sum += brier

            # Log loss
            p = max(ens[actual], 1e-10)
            import math
            logloss_sum += -math.log(p)

        except Exception as e:
            print(f"  ❌ {ht} vs {at}: {e}")

    accuracy = correct / total if total else 0
    brier = brier_sum / total if total else 0
    logloss = logloss_sum / total if total else 0

    print(f"   {correct}/{total} correct ({accuracy:.3f})")
    print(f"   Brier: {brier:.4f}")
    print(f"   LogLoss: {logloss:.4f}")

    return {
        "accuracy": accuracy,
        "brier": brier,
        "log_loss": logloss,
        "correct": correct,
        "total": total,
    }


if __name__ == "__main__":
    main()