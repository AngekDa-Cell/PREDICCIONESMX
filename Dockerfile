# Dockerfile v3 — usa MISMO node version que el host (24.16.0)
# para garantizar compatibilidad del binary de better-sqlite3

FROM node:24.16.0-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

RUN apk add --no-cache libc6-compat

# Copy pre-built standalone output (ya compilado en host con Node 24.16.0)
COPY .next/standalone ./
COPY .next/static ./.next/static
COPY public ./public

# [A.2] Eliminar .env* del bundle para NO exponer secretos como VOTES_TOKEN_SALT.
# Las envs se pasan via --env-file al docker run.
RUN rm -f ./.env ./.env.production ./.env.local ./.env.development ./.env.* && \
    rm -f ./.next/.env ./.next/.env.production ./.next/.env.local

# Verify better-sqlite3 binary matches Node version
RUN node -e "const v = process.version; console.log('Node:', v); console.log('Binary OK:', require('better-sqlite3'))" 2>&1 | head -5

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    chown -R nextjs:nodejs /app

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://172.18.0.2:3000/ > /dev/null 2>&1 || exit 1

CMD ["node", "server.js"]


# ─────────────────────────────────────────────────────────────────────────────
# Build & Run:
# 1. Build Next.js standalone en host (necesita acceso a BD):
#    cd /workspace/quiniela-frontend && npx next build
#
# 2. Build imagen Docker (usa el .next/standalone + public):
#    docker build -t quiniela-frontend:v3 .
#
# 3. Run container:
#    docker run -d --name quiniela-frontend-new \
#      --network back-predicciones_quiniela-net \
#      -v /opt/openclaw/volumes/Predictions_MX/workspace/proyectos/data:/data:ro \
#      -e DATABASE_PATH=/data/predictions_mx.db \
#      -e NODE_ENV=production \
#      --restart unless-stopped \
#      quiniela-frontend:v3