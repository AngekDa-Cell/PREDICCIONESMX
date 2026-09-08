#!/bin/bash
# recalibrate_platt.sh — Recalibra Platt scaling sobre datos frescos.
#
# Flujo:
#   1. Construye dataset de calibración (últimos 800 partidos finalizados).
#   2. Ajusta Platt scaling (1-vs-rest) sobre el ensemble.
#   3. Evalúa out-of-sample (leave-one-season-out) — métrica principal.
#   4. Guarda nuevos coefs en data/platt_coefficients.json (atómico).
#   5. Reporta a Telegram con Δ Brier vs coefs anteriores.
#
# Pensado para correr vía crontab del container (sin LLM, sin retry).
# Si el Δ Brier empeora más del 1pp, NO aplica los nuevos coefs (rollback).
#
# Programado en crontab container:
#   0 9 * * 1 $PROJECT_ROOT/scripts/recalibrate_platt.sh >> $PROJECT_ROOT/data/logs/cron_recalibrate.log 2>&1
#
# Uso manual:
#   ./scripts/recalibrate_platt.sh           # ejecuta, notifica Telegram
#   ./scripts/recalibrate_platt.sh --quiet   # suprime notificación (testing)
#   ./scripts/recalibrate_platt.sh --dry-run # solo build dataset, no fit

set -u

# --- Resolución de paths (parametrizable) ---
# PROJECT_ROOT: auto-detect desde la ubicación del script, override via env.
# CONFIG_FILE: ruta al openclaw.json del agente, override via env.
# Si existe .env en PROJECT_ROOT, se sourcea para exponer DATABASE_URL, etc.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi
CONFIG_FILE="${CONFIG_FILE:-/etc/openclaw/openclaw.json}"

DATASET="$PROJECT_ROOT/data/calibration_dataset.csv"
COEFS="$PROJECT_ROOT/data/platt_coefficients.json"
COEFS_NEW="${COEFS}.new"
COEFS_OLD="${COEFS}.prev"
LOG_DIR="$PROJECT_ROOT/data/logs"
LOG_FILE="$LOG_DIR/cron_recalibrate.log"
N_FIT=800

CHAT_ID="8683821860"  # Ángel

# Flags
QUIET=false
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --quiet) QUIET=true ;;
        --dry-run) DRY_RUN=true ;;
        *) ;;
    esac
done

mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$COEFS")"

# --- Telegram helper (mismo patrón que backup_db.sh) ---
send_telegram() {
    local message="$1"

    if [[ "$QUIET" == "true" ]]; then
        echo "🔕 Telegram skipped (--quiet)"
        return 0
    fi

    local bot_token=""
    if [[ -f "$CONFIG_FILE" ]]; then
        bot_token=$(python3 -c "
import json, sys
try:
    with open('$CONFIG_FILE') as f:
        cfg = json.load(f)
    print(cfg.get('channels', {}).get('telegram', {}).get('botToken', ''))
except Exception:
    sys.exit(0)
" 2>/dev/null)
    fi

    if [[ -z "$bot_token" ]]; then
        echo "⚠️  No Telegram token found"
        return 1
    fi

    python3 - <<PYEOF
import json, urllib.request, urllib.error
message = """$message"""
token = "$bot_token"
chat_id = "$CHAT_ID"
url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = {
    "chat_id": chat_id,
    "text": message,
    "parse_mode": "HTML",
    "disable_web_page_preview": True,
}
try:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()
except Exception as e:
    print(f"Telegram send failed: {e}", file=__import__('sys').stderr)
PYEOF
}

# --- Error handler: notifica Telegram y sale ---
send_error() {
    local lineno="$1"
    local cmd="$2"
    local msg="❌ <b>recalibrate_platt.sh ERROR</b>

Línea: <code>$lineno</code>
Cmd: <code>$cmd</code>

Error: <pre>${ERROR_MSG:-desconocido}</pre>
"
    send_telegram "$msg"
}

# --- Main flow ---
cd "$PROJECT_ROOT" || exit 1
TS_HUMAN=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

# Backup de coefs anteriores (para comparar Δ Brier)
if [[ -f "$COEFS" ]]; then
    cp "$COEFS" "$COEFS_OLD"
    PREV_BRIER=$(python3 -c "
import json
with open('$COEFS_OLD') as f:
    d = json.load(f)
    print(d.get('_oos_brier_post', 0.0))
" 2>/dev/null || echo "0.0")
else
    PREV_BRIER="N/A"
fi

echo "🔄 recalibrate_platt.sh — $TS_HUMAN"
echo "   n_fit=$N_FIT  target=ens  dry_run=$DRY_RUN"
echo ""

# Error trap
trap 'send_error ${LINENO} "BASH_TRAP"' ERR
ERROR_MSG=""

# --- 1. Build dataset ---
echo "▶ 1/2 Build calibration dataset (n=$N_FIT)…"
if ! python3 scripts/build_calibration_dataset.py --last-n "$N_FIT" --output "$DATASET" > "$LOG_DIR/build_cal.log" 2>&1; then
    ERROR_MSG="build_calibration_dataset falló. Log: $LOG_DIR/build_cal.log"
    trap - ERR
    send_error ${LINENO} "build_calibration_dataset"
    exit 1
fi
DATASET_N=$(wc -l < "$DATASET")
DATASET_N=$((DATASET_N - 1))  # restar header
echo "   ✓ $DATASET_N partidos guardados"

if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY RUN: skip fit+save"
    exit 0
fi

# --- 2. Fit Platt scaling ---
echo "▶ 2/2 Fit Platt scaling…"
FIT_OUT=$("$PROJECT_ROOT/scripts/fit_platt_scaling.py" --input "$DATASET" --target ens --output-coefs "$COEFS_NEW" 2>&1)
FIT_EXIT=$?
if [[ $FIT_EXIT -ne 0 ]]; then
    ERROR_MSG="fit_platt_scaling falló (exit=$FIT_EXIT). Output: $FIT_OUT"
    echo "$FIT_OUT" | head -10
    trap - ERR
    send_error ${LINENO} "fit_platt_scaling"
    exit 1
fi

NEW_BRIER=$(python3 -c "
import json
with open('$COEFS_NEW') as f:
    d = json.load(f)
    print(d.get('_oos_brier_post', 0.0))
" 2>/dev/null || echo "?")

DELTA=$(python3 -c "
prev = '$PREV_BRIER'
new = '$NEW_BRIER'
try:
    p = float(prev)
    n = float(new)
    print(f'{(n - p) * 100:+.2f}pp')
except Exception:
    print('N/A')
" 2>/dev/null)

echo "   ✓ OOS Brier previous: $PREV_BRIER  new: $NEW_BRIER  delta: $DELTA"

# --- 3. Validación: si empeora más de 1pp, rollback ---
PREV_FLOAT=$(python3 -c "try: float('$PREV_BRIER'); except: print('inf')" 2>/dev/null)
NEW_FLOAT=$(python3 -c "try: float('$NEW_BRIER'); except: print('inf')" 2>/dev/null)

if [[ "$PREV_FLOAT" != "inf" && "$NEW_FLOAT" != "inf" ]]; then
    DIFF=$(python3 -c "print($NEW_FLOAT - $PREV_FLOAT)" 2>/dev/null)
    if (( $(echo "$DIFF > 0.01" | bc -l 2>/dev/null || echo 0) )); then
        echo "   ⚠️  Delta +${DIFF} > 0.01 (1pp). Rolling back nuevos coefs."
        rm -f "$COEFS_NEW"
        send_telegram "⚠️ <b>recalibrate_platt.sh ROLLBACK</b>

OOS Brier nuevos coefs peoraron: $PREV_BRIER → $NEW_BRIER
Δ: +${DIFF}pp (>1pp threshold).

Coefs NO actualizados. Dataset guardado en <code>$DATASET</code> para análisis."
        exit 0
    fi
fi

# --- 4. Activar nuevos coefs (atómico: rename) ---
mv "$COEFS_NEW" "$COEFS"
echo "   ✓ Coefs actualizados: $COEFS"

# --- 5. Reporte Telegram éxito ---
send_telegram "✅ <b>Platt recalibrado</b>

OOS Brier: <b>$PREV_BRIER → $NEW_BRIER</b> (Δ $DELTA)
n_fit: $N_FIT partidos (últimas ~3 temporadas)

Nuevo modelo activo. Próximo pipeline (11:00 UTC) usará los nuevos coefs."

echo "✅ Done"
