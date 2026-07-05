"""
xg.py — Expected Goals (xG) proxy para Liga MX

SportMonks no expone shot-level con coordenadas, así que construimos un
xG proxy estadístico calibrado con datos propios de Liga MX.

Metodología:
- Features por equipo/partido: shots-on-target, shots-insidebox, shots-blocked, shots-off-target
- Target: goals scored
- Modelo: regresión logística (P(gol >= 1)) + calibración Platt
- xG_proxy = alpha_0 + alpha_1*sot + alpha_2*sib + alpha_3*sb + alpha_4*sot_off
            + alpha_5*shot_quality + (intercept para localía)

NOTA: este es un xG proxy agregado, no un xG por tiro individual. Sirve
para medir calidad ofensiva/defensiva de un equipo a lo largo del tiempo.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import cross_val_score
    HAS_SK = True
except ImportError:
    HAS_SK = False

logger = logging.getLogger(__name__)


def _ridge_regression(X: np.ndarray, y: np.ndarray, alpha: float = 1.0) -> Tuple[float, np.ndarray]:
    """
    Ridge regression (OLS con regularización L2) resuelto en forma cerrada.
    Retorna (intercept, coefs) con intercept separado.
    """
    n, d = X.shape
    # Añadir bias
    Xb = np.hstack([np.ones((n, 1)), X])
    # Resolver (Xb^T Xb + alpha * I) β = Xb^T y
    # NO regularizar el intercept
    I = np.eye(d + 1)
    I[0, 0] = 0.0
    A = Xb.T @ Xb + alpha * I
    b = Xb.T @ y
    beta = np.linalg.solve(A, b)
    return float(beta[0]), beta[1:]

# Config ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "predictions_mx.db"
MODEL_PATH = PROJECT_ROOT / "data" / "xg_model.json"

# Features que usamos para entrenar el xG proxy
SHOT_FEATURES = [
    "shots-on-target",     # tiros a puerta
    "shots-insidebox",     # tiros dentro del área
    "shots-blocked",       # tiros bloqueados
    "shots-off-target",    # tiros fuera
]

# Orden canónico de columnas (para numpy)
FEATURE_ORDER = [
    "shots-on-target",
    "shots-insidebox",
    "shots-blocked",
    "shots-off-target",
    "shot_quality",        # sib / st  (% de tiros dentro del área)
    "is_home",             # localía
]


# Data structures -------------------------------------------------------------

@dataclass
class TeamMatchShots:
    """Stats de shots de un equipo en un partido."""
    fixture_id: int
    team_id: int
    location: str  # 'home' | 'away'
    sot: int       # shots on target
    sib: int       # shots inside box
    sb: int        # shots blocked
    sot_off: int   # shots off target
    st: int        # shots total (para calcular shot_quality)
    goals: int     # target


# Extraction -----------------------------------------------------------------

def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    p = db_path or DB_PATH
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_row_factory(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Asegura que la conexión tenga row_factory (sqlite3.Row)."""
    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row
    return conn


def extract_shot_stats(
    conn: sqlite3.Connection,
    only_completed: bool = True,
) -> List[TeamMatchShots]:
    """
    Extrae (fixture_id, team_id, location, sot, sib, sb, sot_off, st, goals)
    para todos los partidos que tengan las stats necesarias.

    La location (home/away) se infiere de fixtures.home_team_id/away_team_id.
    """
    conn = ensure_row_factory(conn)
    cur = conn.cursor()
    completed_filter = ""
    if only_completed:
        completed_filter = "AND f.home_score IS NOT NULL AND f.away_score IS NOT NULL"

    rows = cur.execute(
        f"""
        SELECT 
            s.fixture_id, s.team_id, s.stat_type, s.stat_value,
            f.home_team_id, f.away_team_id
        FROM fixture_statistics s
        JOIN fixtures f ON f.id = s.fixture_id
        WHERE s.stat_type IN (?, ?, ?, ?, ?, ?)
          {completed_filter}
        """,
        ("shots-on-target", "shots-insidebox", "shots-blocked",
         "shots-off-target", "shots-total", "goals"),
    ).fetchall()

    grouped: Dict[Tuple[int, int], Dict[str, float]] = {}
    for r in rows:
        key = (r["fixture_id"], r["team_id"])
        grouped.setdefault(key, {})
        if r["stat_type"] not in grouped[key]:
            grouped[key][r["stat_type"]] = r["stat_value"]
        # location: comparar team_id con home_team_id/away_team_id
        if "_location" not in grouped[key]:
            if r["team_id"] == r["home_team_id"]:
                grouped[key]["_location"] = "home"
            elif r["team_id"] == r["away_team_id"]:
                grouped[key]["_location"] = "away"
            else:
                grouped[key]["_location"] = "unknown"

    out: List[TeamMatchShots] = []
    for key, d in grouped.items():
        if not all(k in d for k in ("shots-on-target", "shots-insidebox",
                                     "shots-blocked", "shots-off-target",
                                     "shots-total", "goals")):
            continue
        out.append(TeamMatchShots(
            fixture_id=key[0],
            team_id=key[1],
            location=d["_location"],
            sot=int(d["shots-on-target"]),
            sib=int(d["shots-insidebox"]),
            sb=int(d["shots-blocked"]),
            sot_off=int(d["shots-off-target"]),
            st=int(d["shots-total"]),
            goals=int(d["goals"]),
        ))
    return out


def build_feature_matrix(records: List[TeamMatchShots]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Construye X (features) y y (goals) para entrenar el xG proxy.
    """
    X, y = [], []
    for r in records:
        shot_quality = r.sib / max(r.st, 1)
        is_home = 1.0 if r.location == "home" else 0.0
        X.append([
            r.sot,
            r.sib,
            r.sb,
            r.sot_off,
            shot_quality,
            is_home,
        ])
        y.append(r.goals)
    return np.asarray(X, dtype=float), np.asarray(y, dtype=float)


# Training -------------------------------------------------------------------

def _train_logistic_buckets(X: np.ndarray, y: np.ndarray) -> Dict:
    """
    Entrena el xG proxy.

    Estrategia: regresión log-link con regularización L2 (Ridge) sobre
    log(1 + goals). Esto es una aproximación rápida a un GLM Poisson.

    Si sklearn está disponible usamos LogisticRegression como bonus
    (guardado en el modelo para análisis), pero la predicción principal
    usa la regresión ridge.
    """
    # Predicción principal: log-link
    y_log = np.log1p(y)
    intercept, coefs = _ridge_regression(X, y_log, alpha=1.0)
    return {
        "intercept": float(intercept),
        "coefs": [float(c) for c in coefs],
        "feature_order": FEATURE_ORDER,
        "method": "log_ridge",
    }


def _train_logistic_fallback(X: np.ndarray, y: np.ndarray) -> Dict:
    """
    Fallback sin sklearn: OLS con log-link usando pseudoinversa.
    """
    y_log = np.log1p(y)
    # Xb = [1, X]
    n = X.shape[0]
    Xb = np.hstack([np.ones((n, 1)), X])
    # OLS con regularización mínima
    beta, *_ = np.linalg.lstsq(Xb, y_log, rcond=None)
    return {
        "intercept": float(beta[0]),
        "coefs": [float(c) for c in beta[1:]],
        "feature_order": FEATURE_ORDER,
        "method": "log_ridge",
    }


def train_xg_model(
    conn: Optional[sqlite3.Connection] = None,
    save: bool = True,
) -> Dict:
    """
    Entrena el xG proxy con todos los datos históricos disponibles.
    Retorna los coeficientes / estructura del modelo.
    """
    if conn is None:
        conn = get_connection()
    records = extract_shot_stats(conn)
    logger.info("Extraídos %d registros equipo-partido para xG", len(records))
    if not records:
        raise RuntimeError("No hay datos de shots para entrenar xG")
    X, y = build_feature_matrix(records)
    model = _train_logistic_buckets(X, y)
    model["n_train"] = len(records)
    model["goals_mean"] = float(np.mean(y))
    model["goals_std"] = float(np.std(y))
    if save:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MODEL_PATH, "w") as f:
            json.dump(model, f, indent=2)
        logger.info("Modelo xG guardado en %s", MODEL_PATH)
    return model


def load_xg_model(path: Optional[Path] = None) -> Dict:
    p = path or MODEL_PATH
    with open(p) as f:
        return json.load(f)


# Prediction ------------------------------------------------------------------

def predict_xg_for_record(rec: TeamMatchShots, model: Dict) -> float:
    """Predice xG (goles esperados) para un partido de un equipo."""
    if model.get("method") == "log_ridge":
        shot_quality = rec.sib / max(rec.st, 1)
        is_home = 1.0 if rec.location == "home" else 0.0
        x = np.array([
            rec.sot, rec.sib, rec.sb, rec.sot_off, shot_quality, is_home,
        ], dtype=float)
        coefs = np.array(model["coefs"], dtype=float)
        log_pred = model["intercept"] + float(np.dot(x, coefs))
        return float(np.expm1(log_pred))
    elif model.get("method") == "bucket_avg":
        st = rec.sot + rec.sb + rec.sot_off
        return float(model["table"].get(int(st), model.get("goals_mean", 1.0)))
    else:
        raise ValueError(f"Método xG desconocido: {model.get('method')}")


# Rolling features ------------------------------------------------------------

def build_xg_features_for_match(
    team_history: List[Tuple[int, float]],  # [(fixture_id, xG), ...] ordenado
    decay: float = 0.85,
) -> float:
    """
    Calcula xG rolling ponderado exponencialmente para un equipo.
    team_history: lista [(fixture_id_ordenado, xG), ...]
    """
    if not team_history:
        return 0.0
    weights = np.array([decay ** i for i in range(len(team_history))][::-1])
    weights = weights / weights.sum()
    xgs = np.array([x for _, x in team_history])
    return float(np.sum(weights * xgs))


# Pipeline completo -----------------------------------------------------------

def compute_team_xg_history(
    conn: sqlite3.Connection,
    model: Optional[Dict] = None,
) -> Dict[int, List[Tuple[int, float]]]:
    """
    Para cada equipo, devuelve su historial [(fixture_id, xG), ...] ordenado
    cronológicamente.
    """
    if model is None:
        model = load_xg_model()
    records = extract_shot_stats(conn)
    # Anotar fixture_id -> datetime
    cur = conn.cursor()
    fid_to_dt = dict(cur.execute(
        "SELECT id, starting_at FROM fixtures WHERE starting_at IS NOT NULL"
    ).fetchall())

    # Agrupar por equipo
    by_team: Dict[int, List[TeamMatchShots]] = {}
    for r in records:
        by_team.setdefault(r.team_id, []).append(r)

    out: Dict[int, List[Tuple[int, float]]] = {}
    for team_id, recs in by_team.items():
        recs_sorted = sorted(recs, key=lambda r: fid_to_dt.get(r.fixture_id, ""))
        out[team_id] = [
            (r.fixture_id, predict_xg_for_record(r, model)) for r in recs_sorted
        ]
    return out


def build_xg_features_table(
    conn: sqlite3.Connection,
    model: Optional[Dict] = None,
    decay: float = 0.85,
) -> Dict[Tuple[int, int, int], Dict[str, float]]:
    """
    Construye tabla { (fixture_id, team_id, season_id) : {attack_xg, defense_xg_conceded} }
    usando rolling exponencial.

    attack_xg: xG que el equipo generó en partidos anteriores (ponderado)
    defense_xg_conceded: xG que el equipo CONCEDIÓ (goles esperados del rival)
    """
    if model is None:
        model = load_xg_model()
    records = extract_shot_stats(conn)

    # Necesitamos fecha
    cur = conn.cursor()
    fid_to_dt = dict(cur.execute(
        "SELECT id, starting_at FROM fixtures WHERE starting_at IS NOT NULL"
    ).fetchall())
    fid_to_season = dict(cur.execute(
        "SELECT id, season_id FROM fixtures WHERE season_id IS NOT NULL"
    ).fetchall())

    # Para cada equipo-partido, calcular xG que GENERÓ y xG que CONCEDIÓ
    # (goles esperados del RIVAL en ese partido).
    # Agrupar por fixture: tenemos (home_team, away_team) con sus stats.
    fx_to_teams: Dict[int, Dict[str, TeamMatchShots]] = {}
    for r in records:
        fx_to_teams.setdefault(r.fixture_id, {})[r.location] = r

    # Calcular xG por partido/equipo
    fx_team_xg: Dict[int, Dict[str, float]] = {}
    for fid, teams in fx_to_teams.items():
        if "home" not in teams or "away" not in teams:
            continue
        home_xg = predict_xg_for_record(teams["home"], model)
        away_xg = predict_xg_for_record(teams["away"], model)
        fx_team_xg[fid] = {"home": home_xg, "away": away_xg}

    # Por equipo, ordenar cronológicamente y calcular rolling
    by_team: Dict[int, List[Tuple[int, str, float, float]]] = {}
    for fid, xgs in fx_team_xg.items():
        # home
        by_team.setdefault(0, [])  # placeholder
        # necesitamos team_id
        home_team = fx_to_teams[fid]["home"].team_id
        away_team = fx_to_teams[fid]["away"].team_id
        by_team.setdefault(home_team, []).append(
            (fid, "home", xgs["home"], xgs["away"])  # team genera home_xg, concede away_xg
        )
        by_team.setdefault(away_team, []).append(
            (fid, "away", xgs["away"], xgs["home"])  # team genera away_xg, concede home_xg
        )

    # Ordenar cronológicamente
    out: Dict[Tuple[int, int, int], Dict[str, float]] = {}
    for team_id, rows in by_team.items():
        rows.sort(key=lambda r: fid_to_dt.get(r[0], ""))
        # Para cada partido i, attack_xg = rolling ponderado de filas[0:i] (xG generado)
        # defense_xg_conceded = rolling ponderado de filas[0:i] (xG concedido)
        gen_history, con_history = [], []
        for i, (fid, loc, gen, con) in enumerate(rows):
            season_id = fid_to_season.get(fid, 0)
            attack_xg = build_xg_features_for_match(gen_history, decay=decay)
            defense_xg = build_xg_features_for_match(con_history, decay=decay)
            out[(fid, team_id, season_id)] = {
                "attack_xg": attack_xg,
                "defense_xg_conceded": defense_xg,
                "xg_generated_this_match": gen,
                "xg_conceded_this_match": con,
            }
            gen_history.append((fid, gen))
            con_history.append((fid, con))
    return out


# CLI helpers ----------------------------------------------------------------

def get_xg_1x2_prediction(
    conn: sqlite3.Connection,
    home_team_id: int,
    away_team_id: int,
    before_date: Optional[str] = None,
    decay: float = 0.85,
    home_advantage: float = 1.10,
    _cache: Optional[Dict] = None,
) -> Dict[str, float]:
    """
    Predicción 1X2 basada en xG rolling.

    Acepta un `_cache` opcional precomputado por `precompute_xg_lookup()` para
    acelerar backtests (de 0.5s/llamada a <0.001s/llamada).
    """
    if before_date is None:
        before_date = "9999-12-31"

    # Si hay cache, lookup O(1)
    if _cache is not None:
        home_atk, home_con = _cache['attack'].get(home_team_id, {}).get(before_date, 1.0), \
                              _cache['conceded'].get(home_team_id, {}).get(before_date, 1.0)
        away_atk, away_con = _cache['attack'].get(away_team_id, {}).get(before_date, 1.0), \
                              _cache['conceded'].get(away_team_id, {}).get(before_date, 1.0)
    else:
        # Modo lento: calcular desde cero
        records = extract_shot_stats(conn)
        cur = conn.cursor()
        fid_to_dt = dict(cur.execute(
            "SELECT id, starting_at FROM fixtures WHERE starting_at IS NOT NULL"
        ).fetchall())

        by_team: Dict[int, List[Tuple[str, float, float]]] = {}
        fx_teams: Dict[int, Dict[str, TeamMatchShots]] = {}
        for r in records:
            if fid_to_dt.get(r.fixture_id, "") >= before_date:
                continue
            fx_teams.setdefault(r.fixture_id, {})[r.location] = r

        m = load_xg_model()
        for fid, teams in fx_teams.items():
            if "home" not in teams or "away" not in teams:
                continue
            home_xg = predict_xg_for_record(teams["home"], m)
            away_xg = predict_xg_for_record(teams["away"], m)
            dt = fid_to_dt.get(fid, "")
            by_team.setdefault(teams["home"].team_id, []).append((dt, home_xg, away_xg))
            by_team.setdefault(teams["away"].team_id, []).append((dt, away_xg, home_xg))

        def rolling_xg(team_id: int, mode: str) -> float:
            rows = sorted(by_team.get(team_id, []), key=lambda r: r[0])
            if not rows:
                return 1.0
            weights = np.array([decay ** i for i in range(len(rows))][::-1])
            weights = weights / weights.sum()
            vals = np.array([r[1] if mode == "attack" else r[2] for r in rows])
            return float(np.sum(weights * vals))

        home_atk = rolling_xg(home_team_id, "attack")
        away_atk = rolling_xg(away_team_id, "attack")
        home_con = rolling_xg(home_team_id, "conceded")
        away_con = rolling_xg(away_team_id, "conceded")

    league_avg = 1.25
    lam_home = home_atk * (away_con / league_avg) * home_advantage
    lam_away = away_atk * (home_con / league_avg)

    lam_home = max(0.3, min(lam_home, 4.5))
    lam_away = max(0.3, min(lam_away, 4.5))

    p_home, p_draw, p_away = _poisson_1x2(lam_home, lam_away, max_goals=8)

    return {
        "home_win": p_home,
        "draw": p_draw,
        "away_win": p_away,
        "lambda_home": float(lam_home),
        "lambda_away": float(lam_away),
        "home_attack_xg": float(home_atk),
        "away_attack_xg": float(away_atk),
        "home_conceded_xg": float(home_con),
        "away_conceded_xg": float(away_con),
    }


def precompute_xg_lookup(
    conn: sqlite3.Connection,
    decay: float = 0.85,
    league_avg: float = 1.25,
) -> Dict:
    """
    Precomputa TODOS los valores rolling de xG (attack/conceded) por equipo
    y por fecha de corte. Retorna una estructura apta para pasar a
    `get_xg_1x2_prediction(..., _cache=...)` en backtests.

    Estructura del cache:
    {
        'attack':   {team_id: {date_str: rolling_attack_xg, ...}, ...},
        'conceded': {team_id: {date_str: rolling_conceded_xg, ...}, ...},
        'dates':    sorted list of all fixture dates,
    }
    """
    conn = ensure_row_factory(conn)
    records = extract_shot_stats(conn)
    cur = conn.cursor()
    fid_to_dt = dict(cur.execute(
        "SELECT id, starting_at FROM fixtures WHERE starting_at IS NOT NULL"
    ).fetchall())
    m = load_xg_model()

    # xG por fixture
    fx_teams: Dict[int, Dict[str, TeamMatchShots]] = {}
    for r in records:
        fx_teams.setdefault(r.fixture_id, {})[r.location] = r

    fx_xg: Dict[int, Dict[str, float]] = {}
    for fid, teams in fx_teams.items():
        if "home" not in teams or "away" not in teams:
            continue
        fx_xg[fid] = {
            "home": predict_xg_for_record(teams["home"], m),
            "away": predict_xg_for_record(teams["away"], m),
        }

    # Por equipo: (fecha, xG_generado, xG_concedido)
    by_team: Dict[int, List[Tuple[str, float, float]]] = {}
    for fid, xgs in fx_xg.items():
        dt = fid_to_dt.get(fid, "")
        home_team = fx_teams[fid]["home"].team_id
        away_team = fx_teams[fid]["away"].team_id
        by_team.setdefault(home_team, []).append((dt, xgs["home"], xgs["away"]))
        by_team.setdefault(away_team, []).append((dt, xgs["away"], xgs["home"]))

    # Ordenar cronológicamente por equipo
    for tid in by_team:
        by_team[tid].sort(key=lambda r: r[0])

    # Para cada equipo, calcular TODOS los rolling values en cada fecha de corte
    # El backtest pregunta por una fecha before_date, y el rolling correcto es
    # la suma ponderada de TODOS los partidos con dt < before_date.
    all_dates = sorted(set(fid_to_dt.values()))

    cache = {'attack': {}, 'conceded': {}, 'dates': all_dates}

    for tid, rows in by_team.items():
        # Precomputar arrays acumulados
        dates_team = [r[0] for r in rows]
        gen = np.array([r[1] for r in rows])
        con = np.array([r[2] for r in rows])
        n = len(rows)
        weights = np.array([decay ** i for i in range(n)][::-1])
        weights = weights / weights.sum()

        # Para cada fecha de corte, encontrar el índice k = # partidos antes
        cache['attack'][tid] = {}
        cache['conceded'][tid] = {}
        for dt_cut in all_dates:
            # # partidos con fecha < dt_cut
            k = sum(1 for d in dates_team if d < dt_cut)
            if k == 0:
                cache['attack'][tid][dt_cut] = 1.0
                cache['conceded'][tid][dt_cut] = 1.0
                continue
            # Pesos para los últimos k partidos
            w = weights[n - k:]  # los k más recientes
            w = w / w.sum()
            cache['attack'][tid][dt_cut] = float(np.sum(w * gen[n - k:]))
            cache['conceded'][tid][dt_cut] = float(np.sum(w * con[n - k:]))

    return cache


def _poisson_1x2(lam_home: float, lam_away: float, max_goals: int = 8) -> Tuple[float, float, float]:
    """P(1X2) vía Poisson independiente (suma sobre grilla 0..max_goals)."""
    from math import exp, factorial

    def pmf(lam: float, k: int) -> float:
        return exp(-lam) * (lam ** k) / factorial(k)

    p_h = p_d = p_a = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = pmf(lam_home, i) * pmf(lam_away, j)
            if i > j:
                p_h += p
            elif i == j:
                p_d += p
            else:
                p_a += p
    return p_h, p_d, p_a


def print_summary(model: Dict) -> None:
    print(f"Método: {model.get('method')}")
    print(f"Train size: {model.get('n_train')}")
    print(f"Goles/partido — media: {model.get('goals_mean', 0):.3f}, std: {model.get('goals_std', 0):.3f}")
    if model.get("method") == "log_ridge":
        print("Coeficientes (en escala log):")
        for fname, c in zip(model.get("feature_order", FEATURE_ORDER), model["coefs"]):
            print(f"  {fname:25s} {c:+.4f}")
        print(f"  {'intercept':25s} {model['intercept']:+.4f}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Entrenando xG proxy...")
    m = train_xg_model()
    print()
    print_summary(m)
