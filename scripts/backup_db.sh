#!/bin/bash
# backup_db.sh — Backup automático de la BD de Predictions_MX.
#
# Estrategia de retención: SOLO los 3 backups más recientes (ordenados por
# timestamp en el nombre del archivo: predictions_mx_YYYYMMDD_HHMMSS.db).
# Cualquier backup más viejo se borra al finalizar este script.
#
# Uso:
#   ./scripts/backup_db.sh                # backup normal + cleanup
#   ./scripts/backup_db.sh --no-cleanup   # backup sin limpiar viejos

set -e

# Paths
PROJECT_ROOT="/workspace/proyectos"
DB_PATH="$PROJECT_ROOT/data/predictions_mx.db"
BACKUP_DIR="$PROJECT_ROOT/data/backups"
KEEP_LAST=3
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Crear directorio
mkdir -p "$BACKUP_DIR"

# 1. Hacer backup (usar .backup de sqlite para consistencia)
BACKUP_FILE="$BACKUP_DIR/predictions_mx_${TIMESTAMP}.db"
echo "📦 Backup en curso → $BACKUP_FILE"

# SQLite backup atómico (usa SQLITE_API sqlite3_backup_init)
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Verificar
SIZE=$(stat -c %s "$BACKUP_FILE")
SIZE_MB=$((SIZE / 1024 / 1024))
echo "✅ Backup completo: ${SIZE_MB}MB"

# 2. Cleanup (a menos que --no-cleanup)
if [[ "$1" != "--no-cleanup" ]]; then
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

# 3. Reporte
TOTAL=$(find "$BACKUP_DIR" -name "predictions_mx_*.db" -type f | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')
echo ""
echo "📊 Estado de backups:"
echo "   Total: $TOTAL archivos ($TOTAL_SIZE)"
echo "   Path: $BACKUP_DIR"
echo ""
ls -lh "$BACKUP_DIR"