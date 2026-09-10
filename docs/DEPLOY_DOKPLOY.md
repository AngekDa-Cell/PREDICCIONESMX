# Deploy Dokploy — PREDICCIONESMX

> Documentación técnica del deploy en Dokploy.
> Última actualización: 2026-09-10 (commit `cba53bd`)
>
> **Para guía operativa paso-a-paso, ver [`deploy/DOKPLOY.md`](../deploy/DOKPLOY.md).**

---

## 🎯 Visión general

**Dokploy** es el panel de deploy que Ángel eligió para alojar Predictions_MX. Reemplaza el setup previo (VPS + nginx + certbot manual) por una solución más robusta:

- ✅ HTTPS automático con cert wildcard
- ✅ Healthcheck integrado (Traefik + `/api/health`)
- ✅ Multi-stage Dockerfile unifica front + pipeline
- ✅ Logs centralizados (Dokploy + journal)
- ✅ Redeploy sin downtime
- ✅ Bind mount persistente para la BD

**URL de producción:** https://predicciones.barberia.date

---

## 🏗️ Arquitectura del deploy

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     DOKPLOY PANEL (interfaz web)                         │
│  Puerto interno: 3000                                                   │
│  API: container `dokploy.1.g3lrq7z67wiodakf2ofdogoor`                   │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              Traefik (entrypoint websecure)                              │
│  Puerto: 443 (HTTPS)                                                    │
│  Cert wildcard: *.barberia.date (Let's Encrypt via SNI)                  │
│  Routers:                                                                │
│    - predicciones-mx-router@file → predicciones-mx:3000                 │
│    - dokploy.barberia.date → dokploy:3000                                │
│    - seacol.barberia.date → seacol:3000                                  │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│         Container Dokploy: predicciones-mx-app-McpkBWGE8WuNEkG0rFWIL    │
│         (red overlay dokploy-network, 10.0.1.x)                          │
│         Puerto interno: 3000 (no publicado)                              │
│         ─────────────────────────────────────────────────────────────    │
│         USER app (UID 1000)                                             │
│         TZ America/Mexico_City                                           │
│         ─────────────────────────────────────────────────────────────    │
│         PID 1: node server.js (Next.js standalone, :3000)               │
│             └─ /api/health (Traefik readiness probe cada 60s)            │
│             └─ /api/quiniela, /api/votes/[token] (votación)             │
│             └─ /partido/[id], /equipo/[id], /votacion, /voto/[token]    │
│                                                                          │
│         PID secundario: supercronic -no-reap /etc/crontab.app           │
│             └─ 0 11 * * * UTC  python scripts/full_pipeline.py           │
│             └─ 0 4  * * * UTC  bash scripts/backup_db.sh                 │
│             └─ 0 9  * * 1 UTC  bash scripts/recalibrate_platt.sh         │
│                                                                          │
│         Healthcheck: wget -qO- http://127.0.0.1:3000/api/health          │
│         Restart policy: weekly 04:30 UTC                                 │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼ (bind mount)
┌─────────────────────────────────────────────────────────────────────────┐
│              HOST: /srv/predicciones-mx/data                             │
│              Permisos: 1000:1000 (user `app`)                             │
│              ────────────────────────────────────────────────────────     │
│              predictions_mx.db     BD principal (RW para Python, RO bind)│
│              votes_mx.db           BD de votos (RW para Next.js)          │
│              daily_report.{json,txt}  Reporte diario (Telegram-ready)     │
│              backups/             Últimos 3 backups de BD                │
│              logs/                 Logs estructurados de cron             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Recursos Dokploy

### Application

| Atributo | Valor |
|---|---|
| Nombre | `predicciones-mx` |
| Tipo | Application (long-running) |
| Source | GitHub `AngekDa-Cell/PREDICCIONESMX`, branch `main` |
| Build | Docker (auto-detecta `Dockerfile`) |
| Puerto | 3000 (Next.js), no publicado al público |
| Restart | Weekly, 04:30 UTC (preserva BD) |
| App ID | `McpkBWGE8WuNEkG0rFWIL` |

### Bind mount

| Host | Container | Permisos |
|---|---|---|
| `/srv/predicciones-mx/data` | `/workspace/proyectos/data` | `1000:1000` (user `app`) |

> **⚠️ Crítico:** los permisos deben ser `1000:1000`. El Dockerfile crea el user `app` con UID 1000. Sin este chown, las escrituras fallan con `readonly database`.

### Env vars (Dokploy secrets)

| Variable | Tipo | Valor | Notas |
|---|---|---|---|
| `SPORTMONKS_API_TOKEN` | Secret | `<token>` | API plan custom (3000 calls/h) |
| `TELEGRAM_BOT_TOKEN` | Secret | `<token>` | Bot del agente |
| `TELEGRAM_CHAT_ID` | Plain | `8683821860` | Ángel |
| `DATABASE_URL` | Plain | `sqlite:////workspace/proyectos/data/predictions_mx.db` | BD principal |
| `TZ` | Plain | `America/Mexico_City` | TZ del container |
| `LOG_LEVEL` | Plain | `INFO` | Nivel de log |
| `SKIP_DB_CHECK` | Plain | `1` | Deploy inicial sin BD |
| `VOTES_TOKEN_SALT` | Secret | `<random 32+ chars>` | Salt para tokens opacos |
| `VOTES_DATABASE_PATH` | Plain | `/workspace/proyectos/data/votes_mx.db` | BD de votos |
| `DATABASE_PATH` | Plain | `/workspace/proyectos/data/predictions_mx.db` | Path explícito |

### Env vars opcionales (con defaults)

| Variable | Default | Notas |
|---|---|---|
| `SPORTMONKS_BASE_URL` | `https://api.sportmonks.com/v3/football` | |
| `SPORTMONKS_RATE_LIMIT_PER_HOUR` | `2000` | Plan custom: 3000 |
| `SPORTMONKS_LEAGUE_LIGA_MX` | `743` | |
| `SPORTMONKS_LEAGUE_LIGA_EXPANSION` | `749` | |

---

## 🐳 Dockerfile (multi-stage)

**Path:** [`Dockerfile`](../Dockerfile)

### Stage 1: builder (`node:24.16.0-bookworm-slim`)

```dockerfile
FROM node:24.16.0-bookworm-slim AS builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --prefer-offline
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
ENV DATABASE_PATH=/tmp/dummy.db  # Dummy para que next build no falle
RUN touch /tmp/dummy.db && npx next build
```

**¿Por qué `bookworm-slim` y NO `alpine`?**
- `better-sqlite3` requiere compilación nativa contra `glibc` (no musl de Alpine).
- El runtime también usa Debian para compatibilidad binaria.

### Stage 2: runtime (`python:3.12-slim` + Node 24.16.0)

```dockerfile
FROM python:3.12-slim AS runtime

# Sistema: tzdata, sqlite3, bash, curl, xz-utils, ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates sqlite3 tzdata bash xz-utils \
    && rm -rf /var/lib/apt/lists/*

# TZ
ENV TZ=America/Mexico_City
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Node 24.16.0 (mismo que builder, para binary compat de better-sqlite3)
ARG NODE_VERSION=24.16.0
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    | tar -xJ -C /usr/local --strip-components=1

# supercronic (binario estático, sin systemd)
ARG SUPERCRONIC_VERSION=v0.2.33
RUN curl -fsSL \
    "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

# Usuario no-root
RUN groupadd -g 1000 app && useradd -m -u 1000 -g app -s /bin/bash app

WORKDIR /workspace/proyectos

# Deps Python
COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código Python
COPY --chown=app:app src/ ./src/
COPY --chown=app:app scripts/ ./scripts/

# Next.js standalone output (del builder)
COPY --from=builder --chown=app:app /build/.next/standalone ./
COPY --from=builder --chown=app:app /build/.next/static ./.next/static
COPY --from=builder --chown=app:app /build/public ./public/

# Sanitizar .env*
RUN rm -f .env .env.* .env.local .env.production

# Crontab del app (path fijo que entrypoint.sh espera)
COPY --chown=root:root crontab.txt /etc/crontab.app
RUN chmod 0644 /etc/crontab.app

# Entrypoint
COPY --chown=app:app entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Estructura de runtime
RUN mkdir -p data/backups data/logs logs \
    && chown -R app:app data logs

EXPOSE 3000

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/api/health > /dev/null 2>&1 || exit 1

USER app

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

---

## 🚀 Entrypoint (`entrypoint.sh`)

**Path:** [`entrypoint.sh`](../entrypoint.sh)

**Flujo:**

1. **Esperar BD** (si `SKIP_DB_CHECK != 1` y `DATABASE_PATH` no existe):
   ```bash
   for i in $(seq 1 60); do
     [ -f "$DB_PATH" ] && break
     sleep 1
   done
   ```

2. **Arrancar supercronic** (background, PID separado):
   ```bash
   supercronic -no-reap /etc/crontab.app &
   ```
   - `-no-reap`: supercronic NO intenta ser PID 1 (su fork-exec falla cuando lo es).
   - Dokploy ya tiene su reaper → supercronic como PID secundario está OK.

3. **Verificar supercronic vivo:**
   ```bash
   if ! kill -0 "$SUPERCRONIC_PID" 2>/dev/null; then
     echo "❌ supercronic murió al arrancar. Abortando."
     exit 1
   fi
   ```

4. **`exec node server.js`** (PID 1): sirve Next.js en :3000.

---

## ⏰ Cron jobs (`crontab.txt`)

**Path:** [`crontab.txt`](../crontab.txt)

```
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
TZ=UTC

# m h dom mon dow command

# Pipeline diario (10 pasos + quick wins)
0 11 * * * cd /workspace/proyectos && /usr/local/bin/python scripts/full_pipeline.py >> /workspace/proyectos/data/logs/cron_pipeline.log 2>&1

# Backup diario de la BD + reporte Telegram (sin LLM)
0 4 * * * cd /workspace/proyectos && bash scripts/backup_db.sh >> /workspace/proyectos/data/logs/cron_backup.log 2>&1

# Recalibración Platt semanal (lunes)
0 9 * * 1 cd /workspace/proyectos && bash scripts/recalibrate_platt.sh >> /workspace/proyectos/data/logs/cron_recalibrate.log 2>&1
```

**Horas en UTC** (alineadas con convención del proyecto).

**Equivalencias en MX time:**
- `04:00 UTC` = `22:00 CST` (día anterior)
- `09:00 UTC` = `03:00 CST`
- `11:00 UTC` = `05:00 CST`

---

## 🔒 Traefik router

**Path del archivo (en container Dokploy):** `/etc/dokploy/traefik/dynamic/predicciones-mx.yml`

```yaml
http:
  routers:
    predicciones-mx-router:
      rule: "Host(`predicciones.barberia.date`)"
      service: predicciones-mx-service
      entryPoints:
        - websecure
      tls: {}  # ⚠️ CRÍTICO: cert por SNI (wildcard *.barberia.date)
      priority: 34

  services:
    predicciones-mx-service:
      loadBalancer:
        servers:
          - url: "http://predicciones-mx:3000"
```

**⚠️ Lección aprendida (2026-09-10):** un router HTTPS SIN `tls: {}` en entrypoint `websecure` es IGNORADO por Traefik y devuelve 404 default. SIEMPRE declarar `tls: {}` (vacío = cert por SNI).

**Diagnóstico rápido:**
```bash
docker exec dokploy-traefik wget -qO- http://localhost:8080/api/http/routers
docker exec dokploy-traefik wget -qO- http://localhost:8080/api/http/services
```

---

## ✅ Procedimiento de deploy (resumen)

> **Para pasos detallados, ver [`deploy/DOKPLOY.md`](../deploy/DOKPLOY.md).**

1. **Pre-check:** tener `SPORTMONKS_API_TOKEN`, `TELEGRAM_BOT_TOKEN`, `VOTES_TOKEN_SALT` listos como Dokploy secrets.
2. **Crear bind-mount** en Dokploy: `/srv/predicciones-mx/data` con permisos `1000:1000`.
3. **Poblar BD inicial** (si aplica): copiar `predictions_mx.db` existente al host.
4. **Crear Application** Dokploy con source GitHub + Dockerfile auto + env vars.
5. **Trigger deploy** desde Dokploy UI.
6. **Verificar logs** (`docker logs <container>`): debe mostrar `🚀 PREDICCIONES_MX container starting`.
7. **Verificar healthcheck** (`curl https://predicciones.barberia.date/api/health`).
8. **Verificar Traefik router** (debe mostrar el router activo).
9. **Esperar primer cron** (11:00 UTC) → verificar log `data/logs/cron_pipeline.log`.

---

## 🐛 Troubleshooting

### Container reinicia en loop

```bash
docker logs predicciones-mx-app-XXXXX --tail 50
```

**Causas comunes:**
- BD no accesible → verificar bind mount + permisos `1000:1000`
- supercronic falla → verificar formato de `crontab.txt` (debe ser formato vixie cron)
- Variables de entorno faltantes

### Healthcheck falla

```bash
docker exec predicciones-mx-app-XXXXX wget -qO- http://127.0.0.1:3000/api/health
```

**Causas comunes:**
- BD no accesible (mejor-sqlite3 falla al abrir)
- `server.js` no arrancó (revisar logs)

### Traefik devuelve 404

```bash
docker exec dokploy-traefik wget -qO- http://localhost:8080/api/http/routers | grep predicciones
```

**Causa común:** router SIN `tls: {}` → Traefik lo ignora en entrypoint `websecure`. Fix: agregar `tls: {}`.

### Cron no ejecuta

```bash
docker exec predicciones-mx-app-XXXXX supercronic -list /etc/crontab.app
docker exec predicciones-mx-app-XXXXX tail -50 /workspace/proyectos/data/logs/cron_pipeline.log
```

**Causas comunes:**
- Crontab mal copiado (verificar `cat /etc/crontab.app` dentro del container)
- supercronic murió → restart container
- Logs no se escriben → verificar permisos `data/logs/`

### BD readonly

```bash
docker exec predicciones-mx-app-XXXXX ls -la /workspace/proyectos/data/
```

**Causa común:** bind mount sin `chown -R 1000:1000`. Recreate con permisos correctos.

---

## 📚 Ver también

- [`deploy/DOKPLOY.md`](../deploy/DOKPLOY.md) — guía operativa paso a paso
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — arquitectura general (back + front)
- [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) — frontend Next.js
- [`Dockerfile`](../Dockerfile) — multi-stage Dockerfile
- [`entrypoint.sh`](../entrypoint.sh) — entrypoint
- [`crontab.txt`](../crontab.txt) — cron jobs

---

## 🗓️ Historial de deploys

| Fecha | Commit | Cambio |
|---|---|---|
| 2026-09-09 | `2c91269` | Deploy-ready state (Dockerfile, entrypoint.sh, crontab.txt, requirements.txt, .dockerignore, deploy/DOKPLOY.md) |
| 2026-09-09 | `e47fe29` | Fix Dockerfile: COPY crontab.txt a /etc/crontab.app + supercronic -no-reap |
| 2026-09-09 | `c7ac769` | Fix entrypoint.sh: honor SKIP_DB_CHECK=1 |
| 2026-09-10 | `39537a1` | Merge quiniela-frontend + multi-stage Dockerfile (Next.js + Python) |
| 2026-09-10 | `0eef307` | Healthcheck HTTP /api/health endpoint on :3000 |
| 2026-09-10 | `9de7226` | Fix deploy: lazy init votesDb + glibc builder (better-sqlite3 compat) |
| 2026-09-10 | `6b06ce7` | Fix deploy: chown WORKDIR + /workspace/proyectos/logs |
| 2026-09-10 | `2664fff` | feat(db): agregar tabla analyst_predictions al schema (faltante en v2) |
| 2026-09-10 | `cba53bd` | docs: actualizar README y ARCHITECTURE a estado sep 2026 |
