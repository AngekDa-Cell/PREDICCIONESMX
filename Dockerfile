# Dockerfile — PREDICCIONESMX (creado 2026-09-09)
# Base: Python 3.12 slim
# Cron daemon: supercronic (binario estático, sin systemd)
# User: no-root (UID 1000)
# Entry point: entrypoint.sh (wait-for-DB → exec supercronic)

FROM python:3.12-slim AS base

# --- Sistema: tzdata (para TZ=America/Mexico_City), sqlite3 (backups), curl (supercronic) ---
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        sqlite3 \
        tzdata \
        bash \
    && rm -rf /var/lib/apt/lists/*

# --- TZ por defecto (sobrescribible via env) ---
ENV TZ=America/Mexico_City
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# --- Usuario no-root ---
RUN groupadd -g 1000 app \
    && useradd -m -u 1000 -g app -s /bin/bash app

# --- Directorio de trabajo (mantiene el path que esperan los scripts) ---
WORKDIR /workspace/proyectos

# --- supercronic (binario estático, sin systemd) ---
ARG SUPERCRONIC_VERSION=v0.2.33
RUN curl -fsSL \
    "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && supercronic -version || true

# --- Deps Python (capa separada para cache de Docker) ---
COPY --chown=app:app requirements.txt /workspace/proyectos/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /workspace/proyectos/requirements.txt

# --- Código del proyecto (excluye cosas vía .dockerignore) ---
COPY --chown=app:app . /workspace/proyectos/

# --- Estructura de runtime (logs/backups se escriben aquí, montados por Dokploy) ---
RUN mkdir -p /workspace/proyectos/data/backups \
              /workspace/proyectos/data/logs \
    && chown -R app:app /workspace/proyectos/data

# --- entrypoint ---
COPY --chown=app:app entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# --- Healthcheck mínimo: verifica que supercronic siga corriendo ---
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD pgrep -f supercronic >/dev/null || exit 1

USER app

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
