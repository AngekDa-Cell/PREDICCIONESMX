# Deploy en Dokploy — PREDICCIONESMX

Documento vivo. Creado 2026-09-09 al armar el deploy-ready state del repo.

## Arquitectura

- **Tipo:** Aplicación long-running (Dokploy "Application" / Docker mode).
- **Base image:** `python:3.12-slim`.
- **Cron daemon:** `supercronic` (binario estático, no requiere systemd).
- **Usuario:** `app` (UID 1000, no-root).
- **Persistencia BD:** bind-mount `/srv/predicciones-mx/data` → `/workspace/proyectos/data` (preserva el path que esperan los scripts).

## Recursos Dokploy a crear

| Recurso | Tipo | Nombre | Notas |
|---|---|---|---|
| Application | Background | `predicciones-mx` | Único servicio |
| Volume / Bind Mount | `/srv/predicciones-mx/data` → `/workspace/proyectos/data` | SQLite + backups + logs |
| Env vars | (ver abajo) | | |
| Scheduled restart | weekly 04:30 UTC | | Reinicio semanal, mantiene BD |

## Env vars (requeridas)

| Variable | Valor | Notas |
|---|---|---|
| `SPORTMONKS_API_TOKEN` | (Dokploy secret) | Ángel lo inyecta desde Dokploy secrets |
| `TELEGRAM_BOT_TOKEN` | (Dokploy secret) | Bot del agente (mismo que reporta backups) |
| `TELEGRAM_CHAT_ID` | `8683821860` | Chat destino de reportes |
| `DATABASE_URL` | `sqlite:////workspace/proyectos/data/predictions_mx.db` | Path del bind-mount |
| `TZ` | `America/Mexico_City` | |
| `LOG_LEVEL` | `INFO` | |

## Env vars (opcionales, con defaults)

| Variable | Default | Notas |
|---|---|---|
| `SPORTMONKS_BASE_URL` | `https://api.sportmonks.com/v3/football` | |
| `SPORTMONKS_RATE_LIMIT_PER_HOUR` | `2000` | Plan custom Ángel: 3000 |
| `SPORTMONKS_LEAGUE_LIGA_MX` | `743` | |
| `SPORTMONKS_LEAGUE_LIGA_EXPANSION` | `749` | |

## Cron jobs (definidos en `crontab.txt`)

```
0 11 * * *   cd /workspace/proyectos && python scripts/full_pipeline.py
0 4  * * *   cd /workspace/proyectos && bash scripts/backup_db.sh
0 9  * * 1   cd /workspace/proyectos && bash scripts/recalibrate_platt.sh
```

Horas en UTC. El container tiene TZ=America/Mexico_City pero los cron corren en UTC para mantener la convención del proyecto.

## Procedimiento de deploy

1. **Pre-check:** tener `SPORTMONKS_API_TOKEN` listo como Dokploy secret.
2. **Crear bind-mount** en Dokploy: `/srv/predicciones-mx/data` con permisos `1000:1000`.
3. **Poblar BD inicial** (si aplica): copiar `predictions_mx.db` existente al host en `/srv/predicciones-mx/data/`.
4. **Crear Application** Dokploy:
   - Source: GitHub repo `AngekDa-Cell/PREDICCIONESMX`, branch `main`.
   - Build: Docker (auto-detecta `Dockerfile`).
   - Port: ninguno (no hay servidor web).
   - Env vars: ver tabla arriba.
   - Volume mount: como en Recursos.
5. **Deploy.** Esperar a que Dokploy construya y arranque.
6. **Verificar:** `docker logs <container>` → debe mostrar `🚀 PREDICCIONES_MX container starting` + `⏰ Iniciando supercronic...`.

## Verificación post-deploy

```bash
# Logs del container
docker logs <container> --tail 50

# Logs internos (cron)
docker exec <container> tail -20 /workspace/proyectos/data/logs/cron_pipeline.log

# Probar pipeline manualmente
docker exec <container> bash -c "cd /workspace/proyectos && python scripts/full_pipeline.py --dry-run"

# Estado del cron
docker exec <container> bash -c "supercronic -list /etc/crontab.app"
```

## Rotación de secretos post-deploy

1. **GitHub PAT** (re-expuesto en chat 2026-09-09): rotar tras deploy.
2. **SportMonks API token**: si estuvo expuesto, rotar en SportMonks dashboard.
3. **Telegram bot token**: rotar vía @BotFather si expuesto.
4. **Dokploy API token**: rotar vía Dokploy UI.

## Archivos tocados en este deploy-ready state

- `Dockerfile` (NUEVO)
- `entrypoint.sh` (NUEVO)
- `crontab.txt` (NUEVO)
- `requirements.txt` (NUEVO, consolidado)
- `.dockerignore` (NUEVO)
- `deploy/DOKPLOY.md` (NUEVO, este doc)
- `src/config.py` (MODIFICADO: `TZ` default `Europe/Berlin` → `America/Mexico_City`)
- `scripts/backup_db.sh` (MODIFICADO: lee `TELEGRAM_BOT_TOKEN` de env primero)
- `scripts/recalibrate_platt.sh` (MODIFICADO: mismo)
- `.env.example` (MODIFICADO: añade `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATABASE_URL`)
