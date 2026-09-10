#!/bin/bash
# entrypoint.sh — PREDICCIONESMX (creado 2026-09-09)
# Espera a que la BD SQLite esté disponible (bind-mount), luego exec supercronic.
# No toca la BD, no la crea. Si no existe, espera 60s y sale con error.

set -euo pipefail

echo "🚀 PREDICCIONES_MX container starting"
echo "   TZ=${TZ:-<unset>}"
echo "   PROJECT_ROOT=$(pwd)"
echo "   USER=$(whoami)"
echo "   DATABASE_URL=${DATABASE_URL:-<unset>}"

# --- Resolver path de la BD desde DATABASE_URL (sqlite:///...) ---
DB_PATH=""
if [ -n "${DATABASE_URL:-}" ]; then
    DB_PATH=$(echo "$DATABASE_URL" | sed -E 's|^sqlite:(///)|/|; s|^sqlite://(/)|\1|')
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

# --- Arrancar supercronic en foreground (PID 1 lo hereda Dokploy) ---
# -no-reap: supercronic como PID 1 falla su fork-exec interno de reaping
# ("Failed to fork exec: no such file or directory"). Dokploy ya tiene su
# propio reaper, así que no perdemos nada.
echo "⏰ Iniciando supercronic..."
exec supercronic -no-reap /etc/crontab.app
