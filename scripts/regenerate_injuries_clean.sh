#!/bin/bash
# Regenera BD limpia de lesiones después de tests.
# Útil cuando se quieren borrar lesiones manuales/sintéticas.
cd /workspace/proyectos
sqlite3 data/predictions_mx.db "DELETE FROM player_injuries WHERE source != 'espn_api_v2'"
echo "✅ Lesiones manuales/sintéticas borradas. Solo ESPN API permanece."
