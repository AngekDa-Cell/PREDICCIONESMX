#!/usr/bin/env python3
"""
Test extremo del feature de lesiones:
- Lesiones MUY asimétricas (1 equipo con 3 Out, otro 0)
- Weight=0.15 (más fuerte)
- Mide si el feature cambia picks en casos extremos
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path('/workspace/proyectos')))
sys.path.insert(0, str(Path('/workspace/proyectos/src')))

import sqlite3
import json
import math
from datetime import datetime

conn = sqlite3.connect('/workspace/proyectos/data/predictions_mx.db')

# Cargar features
from predict.features import get_player_injuries_impact
from predict.backtest import predict_match

# Partido test: América vs Chivas (pretemporada, sin lesiones reales)
home_id, away_id = 2687, 427
season_id = 28009
fixture_date = '2026-07-20T20:00:00'

# Limpiar lesiones manuales
conn.execute("DELETE FROM player_injuries WHERE source = 'manual'")
conn.commit()

print("🧪 TEST EXTREMO — Lesiones asimétricas")
print("=" * 70)

# Baseline
p_baseline = predict_match(conn, home_id, away_id, season_id, fixture_date, {"narratives":[], "derbies":[]})
ens = p_baseline['ensemble']
print(f"\n📊 Baseline (sin lesiones):")
print(f"   H={ens['home']:.3f} D={ens['draw']:.3f} A={ens['away']:.3f}")
print(f"   Pick: {max(ens, key=ens.get).upper()} ({max(ens.values()):.1%})")

# Caso 1: 3 Out a Chivas (visitante)
print(f"\n📊 Caso 1: Chivas con 3 lesionados Out (visitante)")
key_players_chivas = conn.execute("""
    SELECT p.id, p.full_name FROM players p, fixture_lineups fl
    WHERE p.id = fl.player_id
      AND JSON_EXTRACT(p.meta_json, '$.team_id') = ?
      AND fl.is_starter = 1
    GROUP BY p.id
    ORDER BY COUNT(*) DESC LIMIT 3
""", (away_id,)).fetchall()
print(f"   Titulares Chivas identificados: {len(key_players_chivas)}")
for pid, name in key_players_chivas:
    print(f"     - {name} (id={pid})")
    conn.execute("""
        INSERT INTO player_injuries
        (player_id, team_id, season_id, start_date, end_date, injury_type, severity, source, meta_json)
        VALUES (?, ?, ?, '2026-07-10', '2026-08-15', 'Lesión', 'Out', 'manual', '{}')
    """, (pid, away_id, season_id))
conn.commit()

p = predict_match(conn, home_id, away_id, season_id, fixture_date, {"narratives":[], "derbies":[]})
ens = p['ensemble']
inj = get_player_injuries_impact(conn, away_id, fixture_date)
print(f"   Away injury impact: {inj['total_impact']:.3f}")
print(f"   H={ens['home']:.3f} D={ens['draw']:.3f} A={ens['away']:.3f}")
print(f"   Pick: {max(ens, key=ens.get).upper()} ({max(ens.values()):.1%})")

# Caso 2: 3 Out a AMÉRICA (local)
print(f"\n📊 Caso 2: AMÉRICA con 3 lesionados Out (local)")
conn.execute("DELETE FROM player_injuries WHERE source = 'manual'")
conn.commit()
key_players_america = conn.execute("""
    SELECT p.id, p.full_name FROM players p, fixture_lineups fl
    WHERE p.id = fl.player_id
      AND JSON_EXTRACT(p.meta_json, '$.team_id') = ?
      AND fl.is_starter = 1
    GROUP BY p.id
    ORDER BY COUNT(*) DESC LIMIT 3
""", (home_id,)).fetchall()
for pid, name in key_players_america:
    print(f"     - {name} (id={pid})")
    conn.execute("""
        INSERT INTO player_injuries
        (player_id, team_id, season_id, start_date, end_date, injury_type, severity, source, meta_json)
        VALUES (?, ?, ?, '2026-07-10', '2026-08-15', 'Lesión', 'Out', 'manual', '{}')
    """, (pid, home_id, season_id))
conn.commit()

p = predict_match(conn, home_id, away_id, season_id, fixture_date, {"narratives":[], "derbies":[]})
ens = p['ensemble']
inj = get_player_injuries_impact(conn, home_id, fixture_date)
print(f"   Home injury impact: {inj['total_impact']:.3f}")
print(f"   H={ens['home']:.3f} D={ens['draw']:.3f} A={ens['away']:.3f}")
print(f"   Pick: {max(ens, key=ens.get).upper()} ({max(ens.values()):.1%})")

# Caso 3: 5 Out a Chivas + 0 a América (extremo)
print(f"\n📊 Caso 3: EXTREMO — Chivas 5 Out, América 0")
conn.execute("DELETE FROM player_injuries WHERE source = 'manual'")
conn.commit()
key_players_chivas_5 = conn.execute("""
    SELECT p.id, p.full_name FROM players p, fixture_lineups fl
    WHERE p.id = fl.player_id
      AND JSON_EXTRACT(p.meta_json, '$.team_id') = ?
      AND fl.is_starter = 1
    GROUP BY p.id
    ORDER BY COUNT(*) DESC LIMIT 5
""", (away_id,)).fetchall()
for pid, name in key_players_chivas_5:
    conn.execute("""
        INSERT INTO player_injuries
        (player_id, team_id, season_id, start_date, end_date, injury_type, severity, source, meta_json)
        VALUES (?, ?, ?, '2026-07-10', '2026-08-15', 'Lesión', 'Out', 'manual', '{}')
    """, (pid, away_id, season_id))
conn.commit()

p = predict_match(conn, home_id, away_id, season_id, fixture_date, {"narratives":[], "derbies":[]})
ens = p['ensemble']
inj = get_player_injuries_impact(conn, away_id, fixture_date)
print(f"   Away injury impact: {inj['total_impact']:.3f} (suma de 5 Out)")
print(f"   H={ens['home']:.3f} D={ens['draw']:.3f} A={ens['away']:.3f}")
print(f"   Pick: {max(ens, key=ens.get).upper()} ({max(ens.values()):.1%})")

# Limpiar
conn.execute("DELETE FROM player_injuries WHERE source = 'manual'")
conn.commit()
conn.close()

print("\n" + "=" * 70)
print("✅ Test completado. Si los 3 casos muestran diferencias claras en el")
print("   pick o en las probs, el feature FUNCIONA. Solo falta validar en")
print("   la temporada real (agosto-mayo).")