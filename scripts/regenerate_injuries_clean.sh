#!/bin/bash
# Regenera BD limpia de lesiones después de tests.
# Útil cuando se quieren borrar lesiones manuales/sintéticas.
# Paths parametrizables (override via env).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
DB_PATH="${DB_PATH:-$PROJECT_ROOT/data/predictions_mx.db}"
cd "$PROJECT_ROOT"
sqlite3 "$DB_PATH" "DELETE FROM player_injuries WHERE source != 'espn_api_v2'"
echo "✅ Lesiones manuales/sintéticas borradas. Solo ESPN API permanece."
