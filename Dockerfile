# Dockerfile — PREDICCIONESMX (multi-stage: Next.js front + Python pipeline)
# Stage 1 (builder): compila Next.js standalone con Node 24.16.0
# Stage 2 (runtime): Python 3.12 + Node 24.16.0-alpine + supercronic
#   - supercronic ejecuta cron jobs (ingest/predict/backup/recalibrate)
#   - node server.js sirve el front Next.js en :3000
#   - Traefik healthcheck via /api/health (Next.js)

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder — compila Next.js standalone
# ─────────────────────────────────────────────────────────────────────────────
FROM node:24.16.0-alpine AS builder

WORKDIR /build

# Deps primero (capa cacheable)
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --prefer-offline

# Código fuente
COPY . .

# Build con BD dummy (lazy init en lib/db/client.ts evita abrir al import).
# Next.js necesita esto para resolver imports durante la compilación.
# No usamos BD real aquí; el lazy init del cliente evita I/O en build-time.
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
ENV DATABASE_PATH=/tmp/dummy.db
RUN touch /tmp/dummy.db && npx next build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime — Python + Node + supercronic
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# --- Sistema: tzdata, sqlite3, bash, curl (supercronic), libc6-compat (Node alpine bin) ---
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        sqlite3 \
        tzdata \
        bash \
        libc6-compat \
    && rm -rf /var/lib/apt/lists/*

# --- TZ por defecto ---
ENV TZ=America/Mexico_City
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# --- Node 24.16.0 runtime (mismo que builder, para binary compat de better-sqlite3) ---
ARG NODE_VERSION=24.16.0
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    | tar -xJ -C /usr/local --strip-components=1 \
    && node -v && npm -v

# --- supercronic (binario estático, sin systemd) ---
ARG SUPERCRONIC_VERSION=v0.2.33
RUN curl -fsSL \
    "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && supercronic -version || true

# --- Usuario no-root ---
RUN groupadd -g 1000 app \
    && useradd -m -u 1000 -g app -s /bin/bash app

# --- Directorio de trabajo (mantiene path que esperan los scripts Python) ---
WORKDIR /workspace/proyectos

# --- Deps Python (capa cacheable) ---
COPY --chown=app:app requirements.txt /workspace/proyectos/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /workspace/proyectos/requirements.txt

# --- Código Python del proyecto ---
COPY --chown=app:app src/ /workspace/proyectos/src/
COPY --chown=app:app scripts/ /workspace/proyectos/scripts/
COPY --chown=app:app data/ /workspace/proyectos/data/
COPY --chown=app:app tests/ /workspace/proyectos/tests/

# --- Next.js standalone output (del builder) ---
COPY --from=builder --chown=app:app /build/.next/standalone /workspace/proyectos/
COPY --from=builder --chown=app:app /build/.next/static /workspace/proyectos/.next/static
COPY --from=builder --chown=app:app /build/public /workspace/proyectos/public 2>/dev/null || true

# --- Sanitizar: nada de .env* en la imagen ---
RUN rm -f /workspace/proyectos/.env /workspace/proyectos/.env.* \
            /workspace/proyectos/.env.local /workspace/proyectos/.env.production

# --- Crontab del app (path fijo que entrypoint.sh espera) ---
COPY --chown=root:root crontab.txt /etc/crontab.app
RUN chmod 0644 /etc/crontab.app

# --- entrypoint ---
COPY --chown=app:app entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# --- Estructura de runtime ---
RUN mkdir -p /workspace/proyectos/data/backups \
              /workspace/proyectos/data/logs \
    && chown -R app:app /workspace/proyectos/data

# --- Puertos ---
EXPOSE 3000

# --- Healthcheck vía Next.js /api/health ---
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/api/health > /dev/null 2>&1 || exit 1

USER app

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
