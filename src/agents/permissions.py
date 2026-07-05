"""
permissions.py — Definición de permisos por agente (Fase 10).

Restricción dura (Ángel 2026-06-27): agentes NO pueden modificar el VPS.
Cada agente se lanza con `sessions_spawn(toolsAllow=[...], sandbox="require")`
y solo puede usar las tools de su rol. Cualquier intento de tool bloqueada
debe ser registrado como incidente de seguridad.

🔒 FIX APLICADO 2026-06-27 (Fase 10.2): sub-agentes usan sandbox="require"
para que NO hereden el workspace del parent. Antes, un sub-agente podía
acceder a la BD SQLite del parent aunque exec no estuviera en su toolsAllow.

Decisión de diseño: bull/bear/contextual son SOLO LECTURA. Numérico
puede ejecutar queries SQLite (read-only por convención, sin DROP/DELETE).
Juez solo lee outputs de otros agentes.
"""

from typing import List, Dict


# Tools permitidas por rol
# ⚠️ Cada rol tiene una lista EXPLÍCITA de permitidas. Si no está aquí, está DENEGADA.

# 🔒 TODOS los sub-agentes usan sandbox="require" en sessions_spawn,
# lo que evita que hereden el workspace del parent (incluyendo acceso a SQLite).

READ_ONLY_BASE = ["read", "memory_search", "memory_get"]

BULL_LOCAL_TOOLS = READ_ONLY_BASE + ["web_search", "web_fetch"]
"""
Bull-Local: lee features, busca contexto cualitativo (web), consulta memoria.
NO puede escribir, ejecutar comandos, tocar VPS ni Docker.
Sandbox: aislado del parent workspace.
"""

BEAR_VISITANTE_TOOLS = READ_ONLY_BASE + ["web_search", "web_fetch"]
"""
Bear-Visitante: misma estructura que Bull, prompts opuestos.
Sandbox: aislado del parent workspace.
"""

NUMERICO_TOOLS = READ_ONLY_BASE + ["exec"]
"""
Numérico (Predictions_MX): ejecuta el ensemble actual (queries SQLite
sobre data/predictions_mx.db). Solo lectura por convención. NO usa
write/edit/gateway/process/nodes.
NOTA: Numérico normalmente corre LOCAL (no como sub-agente) porque
necesita acceso directo a la BD del workspace.
"""

CONTEXTUAL_TOOLS = READ_ONLY_BASE + ["web_search", "web_fetch"]
"""
Contextual (F10.2): agrega noticias recientes vía web_search/web_fetch.
Mismas restricciones que Bull/Bear.
"""

DATA_AUDITOR_TOOLS = READ_ONLY_BASE + ["exec"]
"""
Auditor de Datos: ejecuta queries SQLite de validación. Solo lectura.
Reporta issues, no los corrige.
"""

JUEZ_TOOLS = READ_ONLY_BASE
"""
Juez: solo lee outputs de otros agentes. Sin web, sin exec, sin write.
Pondera con DWC-MAD basándose en confianza y métricas históricas.
"""


# Mapa de permisos por rol
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "bull_local": BULL_LOCAL_TOOLS,
    "bear_visitante": BEAR_VISITANTE_TOOLS,
    "numerico": NUMERICO_TOOLS,
    "contextual": CONTEXTUAL_TOOLS,
    "data_auditor": DATA_AUDITOR_TOOLS,
    "juez": JUEZ_TOOLS,
}


def get_tools_for_role(role: str) -> List[str]:
    """Retorna toolsAllow para un rol. Lanza KeyError si rol no existe."""
    if role not in ROLE_PERMISSIONS:
        raise KeyError(
            f"Rol desconocido: {role}. Roles válidos: {list(ROLE_PERMISSIONS.keys())}"
        )
    return ROLE_PERMISSIONS[role]


def is_tool_allowed(role: str, tool: str) -> bool:
    """Verifica si un tool está permitido para un rol."""
    return tool in get_tools_for_role(role)


def get_sandbox_for_role(role: str) -> str:
    """
    Retorna el sandbox policy para un rol.
    
    Por defecto, todos los sub-agentes usan 'require' (aislado del parent workspace)
    para que NO hereden acceso a archivos o BD del parent.
    
    Returns:
        "require" para todos los roles (cambiar si necesitas acceso compartido)
    """
    return "require"  # Siempre aislado (FIX 2026-06-27)


# Validación de seguridad post-spawn (referencia para tests)
FORBIDDEN_TOOLS = ["write", "edit", "gateway", "process", "nodes", "cron", "message", "canvas", "browser", "image"]

# Tools que requieren especial precaución
DANGEROUS_PATTERNS = {
    "exec": ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "docker", "rm ", "kubectl"],
}
"""
Patrones DENTRO de exec que están prohibidos incluso si exec está permitido.
El orquestador debe filtrar antes de ejecutar (defense in depth).
"""
