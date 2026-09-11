#!/bin/bash
# backup_db.sh — Backup automático de la BD de Predictions_MX con auto-reporte a Telegram.
#
# Estrategia de retención: SOLO los 3 backups más recientes (ordenados por
# timestamp en el nombre del archivo: predictions_mx_YYYYMMDD_HHMMSS.db).
# Cualquier backup más viejo se borra al finalizar este script.
#
# Al terminar (éxito o error) el script manda reporte directo a Telegram vía
# curl/python, sin pasar por el LLM. Esto elimina la dependencia del modelo
# para el flujo normal del cron.
#
# Uso:
#   ./scripts/backup_db.sh                # backup normal + cleanup + reporte Telegram
#   ./scripts/backup_db.sh --no-cleanup   # backup sin limpiar viejos + reporte
#   ./scripts/backup_db.sh --test         # solo manda mensaje de prueba (sin backup)
#   ./scripts/backup_db.sh --quiet        # suprime el reporte Telegram (para cron manual)

set -u

# Paths (parametrizables; auto-detect si no se exportan)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi
DB_PATH="${DB_PATH:-$PROJECT_ROOT/data/predictions_mx.db}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/data/backups}"
KEEP_LAST=3
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Telegram config (env primero, fallback a CONFIG_FILE del agente para dev local)
CHAT_ID="${TELEGRAM_CHAT_ID:-8683821860}"  # Ángel
CONFIG_FILE="${CONFIG_FILE:-/opt/openclaw/predicciones/config/openclaw.json}"

# Flags
SEND_TELEGRAM=true
QUIET=false
TEST_MODE=false

for arg in "$@"; do
    case "$arg" in
        --no-cleanup) ;;  # handled inline below
        --test) TEST_MODE=true ;;
        --quiet) QUIET=true ;;
        *) ;;
    esac
done

# --- Telegram helper (sin LLM, solo curl/python) ---
send_telegram() {
    local message="$1"

    if [[ "$QUIET" == "true" ]]; then
        echo "🔕 Telegram skipped (--quiet)"
        return 0
    fi

    local bot_token="${TELEGRAM_BOT_TOKEN:-}"
    if [[ -z "$bot_token" && -f "$CONFIG_FILE" ]]; then
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
        echo "⚠️  No Telegram token found (env TELEGRAM_BOT_TOKEN o CONFIG_FILE), notification skipped"
        return 1
    fi

    # [SECURITY FIX 2026-09-10] Pasar valores vía env vars, NO heredoc interpolation.
    # El patrón anterior interpolaba $message dentro del código python,
    # exponiendo a command injection si message contenía backticks o $(...)
    # (bash los interpretaba ANTES de pasar a python). Ahora:
    # - <<'PYEOF' (quoted) desactiva toda expansion de variables en el heredoc.
    # - Valores sensibles llegan por env vars (literal, sin re-interpretacion).
    TELEGRAM_BOT_TOKEN_VALUE="$bot_token" \
    TELEGRAM_CHAT_ID_VALUE="$CHAT_ID" \
    TELEGRAM_MESSAGE_VALUE="$message" \
    python3 <<'PYEOF'
import os, json, urllib.request, urllib.error, sys

token = os.environ["TELEGRAM_BOT_TOKEN_VALUE"]
chat_id = os.environ["TELEGRAM_CHAT_ID_VALUE"]
message = os.environ["TELEGRAM_MESSAGE_VALUE"]

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
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        if data.get("ok"):
            print("📨 Telegram: ✅ delivered")
        else:
            print(f"📨 Telegram: ⚠️ {data.get('description', 'unknown error')}")
            sys.exit(1)
except urllib.error.HTTPError as e:
    print(f"📨 Telegram: ❌ HTTP {e.code} {e.reason}")
    sys.exit(1)
except Exception as e:
    print(f"📨 Telegram: ❌ {type(e).__name__}: {e}")
    sys.exit(1)
PYEOF
}

# --- Test mode ---
if [[ "$TEST_MODE" == "true" ]]; then
    echo "🧪 Modo test — enviando solo mensaje de prueba a Telegram"
    send_telegram "🧪 <b>Test backup_db.sh</b>

Si ves este mensaje, el auto-reporte a Telegram está funcionando.
Modo: test (no se hizo backup)
🕐 ${TIMESTAMP:0:4}-${TIMESTAMP:4:2}-${TIMESTAMP:6:2} ${TIMESTAMP:9:2}:${TIMESTAMP:11:2}:${TIMESTAMP:13:2} UTC"
    exit $?
fi

# --- Main backup flow ---
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/predictions_mx_${TIMESTAMP}.db"
echo "📦 Backup en curso → $BACKUP_FILE"

# Error handler: manda Telegram de error y sale sin retry (2026-07-15)
send_error() {
    local lineno="$1"
    local cmd="$2"
    local TS_HUMAN="${TIMESTAMP:0:4}-${TIMESTAMP:4:2}-${TIMESTAMP:6:2} ${TIMESTAMP:9:2}:${TIMESTAMP:11:2}:${TIMESTAMP:13:2} UTC"
    send_telegram "❌ <b>Backup diario FALLÓ</b>

⚠️ Error en línea <code>${lineno}</code>: <code>${cmd}</code>
🕐 ${TS_HUMAN}"
    exit 1
}

# Trap para capturar errores → manda Telegram de error y sale (sin retry)
set -e
trap 'send_error "${LINENO}" "${BASH_COMMAND}"' ERR

# SQLite backup atómico (usa SQLITE_API sqlite3_backup_init)
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Verificar
SIZE=$(stat -c %s "$BACKUP_FILE")
SIZE_MB=$((SIZE / 1024 / 1024))
echo "✅ Backup completo: ${SIZE_MB}MB"

# Cleanup (a menos que --no-cleanup)
if [[ "${1:-}" != "--no-cleanup" ]]; then
    echo "🧹 Limpiando backups viejos (manteniendo últimos $KEEP_LAST)..."

    # Ordenar por nombre (formato YYYYMMDD_HHMMSS → orden cronológico)
    # y borrar todos excepto los KEEP_LAST primeros.
    cd "$BACKUP_DIR"
    TO_DELETE=$(ls -1 predictions_mx_*.db 2>/dev/null \
        | sort -r \
        | tail -n +$((KEEP_LAST + 1)))

    if [[ -n "$TO_DELETE" ]]; then
        echo "$TO_DELETE" | xargs -r rm -f
    fi

    DELETED=$(echo -n "$TO_DELETE" | grep -c . 2>/dev/null || echo 0)
    REMAINING=$(ls -1 predictions_mx_*.db 2>/dev/null | wc -l)

    echo "   Borrados: $DELETED | Quedan: $REMAINING"
fi

# Reporte local
TOTAL=$(find "$BACKUP_DIR" -name "predictions_mx_*.db" -type f | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')

# Reset trap
trap - ERR

echo ""
echo "📊 Estado de backups:"
echo "   Total: $TOTAL archivos ($TOTAL_SIZE)"
echo "   Path: $BACKUP_DIR"
echo ""
ls -lh "$BACKUP_DIR"

# --- Reporte a Telegram (vía curl, sin LLM) ---
TS_HUMAN="${TIMESTAMP:0:4}-${TIMESTAMP:4:2}-${TIMESTAMP:6:2} ${TIMESTAMP:9:2}:${TIMESTAMP:11:2}:${TIMESTAMP:13:2} UTC"

TELEGRAM_MSG="✅ <b>Backup diario OK</b>

📦 Archivo: <code>predictions_mx_${TIMESTAMP}.db</code>
💾 Tamaño: <b>${SIZE_MB} MB</b>
🗂  Total backups: ${TOTAL}
💽 Espacio usado: ${TOTAL_SIZE}
🕐 ${TS_HUMAN}"

send_telegram "$TELEGRAM_MSG"

exit 0
