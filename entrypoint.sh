#!/bin/bash
# entrypoint.sh — PREDICCIONESMX (multi-stage: Next.js + Python pipeline)
# 1. Espera BD SQLite si está configurada.
# 2. Arranca supercronic en background (cron jobs Python: ingest/predict/backup).
# 3. exec node server.js (PID 1) — Next.js front en :3000.
# 4. Healthcheck via /api/health (Next.js route).

set -euo pipefail

echo "🚀 PREDICCIONES_MX container starting (multi-stage: Next.js + Python pipeline)"
echo "   TZ=${TZ:-<unset>}"
echo "   PROJECT_ROOT=$(pwd)"
echo "   USER=$(whoami)"
echo "   DATABASE_URL=${DATABASE_URL:-<unset>}"
echo "   DATABASE_PATH=${DATABASE_PATH:-<unset>}"

# --- Resolver path de la BD desde DATABASE_URL o DATABASE_PATH ---
DB_PATH=""
if [ -n "${DATABASE_URL:-}" ]; then
    DB_PATH=$(echo "$DATABASE_URL" | sed -E 's|^sqlite:(///)|/|; s|^sqlite://(/)|\1|')
elif [ -n "${DATABASE_PATH:-}" ]; then
    DB_PATH="$DATABASE_PATH"
fi

# --- Esperar a la BD si no existe (salteable con SKIP_DB_CHECK=1) ---
WAIT_SECONDS=60
if [ -n "$DB_PATH" ] && [ "${SKIP_DB_CHECK:-0}" != "1" ] && [ ! -f "$DB_PATH" ]; then
    echo "⏳ Esperando BD en $DB_PATH (max ${WAIT_SECONDS}s)..."
    for i in $(seq 1 $WAIT_SECONDS); do
        if [ -f "$DB_PATH" ]; then
            echo "✅ BD encontrada tras ${i}s"
            break
        fi
        sleep 1
    done
    if [ ! -f "$DB_PATH" ]; then
        echo "❌ BD no apareció tras ${WAIT_SECONDS}s."
        echo "   Si es deploy inicial: monta un volumen con la BD ya poblada."
        echo "   Para forzar inicio sin BD: SKIP_DB_CHECK=1"
        exit 1
    fi
fi

# --- Mostrar crontab activo (debug) ---
echo "📋 Crontab activo:"
cat /etc/crontab.app | sed 's/^/   /'

# --- Arrancar supercronic en background (PID separado, lo reapa Dokploy) ---
# -no-reap: supercronic como PID 1 falla su fork-exec interno; aquí NO es PID 1
# (lo es node server.js), así que el reap pasa a node.
echo "⏰ Iniciando supercronic en background..."
supercronic -no-reap /etc/crontab.app &
SUPERCRONIC_PID=$!
echo "   supercronic PID: ${SUPERCRONIC_PID}"

# --- Dar tiempo a supercronic a leer crontab ---
sleep 2

# --- Verificar que supercronic sigue vivo antes de levantar el front ---
if ! kill -0 "$SUPERCRONIC_PID" 2>/dev/null; then
    echo "❌ supercronic murió al arrancar. Abortando."
    exit 1
fi

# --- exec node server.js (PID 1, foreground) — Next.js front ---
# Next.js standalone produce server.js en /workspace/proyectos/server.js
echo "🎨 Iniciando Next.js (PID 1)..."
exec node server.js
