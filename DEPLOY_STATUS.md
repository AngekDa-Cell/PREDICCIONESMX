# Deploy Status — quiniela-frontend (Fase 10.3)

**Fecha:** 2026-06-27
**Estado:** 🟡 6/7 pasos completos — pendiente nginx reload manual

---

## ✅ Lo que YA está listo

| # | Componente | Ubicación | Status |
|---|---|---|---|
| 1 | Container del frontend | `quiniela-frontend-new` en `back-predicciones_quiniela-net` (172.17.0.2 + 172.18.0.2) | ✅ Up 11min |
| 2 | Config nginx | `/etc/nginx/sites-available/quinielas.lol.conf` | ✅ 1205 bytes |
| 3 | Symlink | `/etc/nginx/sites-enabled/quinielas.lol.conf` | ✅ Activo |
| 4 | Imagen Docker | `quiniela-frontend:v1` | ✅ Built |
| 5 | Code base | `/workspace/quiniela-frontend/` | ✅ Compila OK |
| 6 | BD bind mount | `/workspace/proyectos/data:/workspace/proyectos/data:ro` | ✅ Montada |

## ❌ Lo que FALTA (necesita ejecución manual del host)

| # | Paso | Comando a ejecutar |
|---|---|---|
| 1 | Copiar cert autofirmado al host | `cp /workspace/quiniela-frontend/certs/quinielas.lol.crt /etc/nginx/certs/ && cp /workspace/quiniela-frontend/certs/quinielas.lol.key /etc/nginx/certs/` |
| 2 | Validar nginx config | `nginx -t` |
| 3 | Arrancar nginx (o reload si ya corre) | `nginx` o `systemctl reload nginx` |
| 4 | (Opcional pero recomendado) Generar cert válido con certbot | `certbot --nginx -d quinielas.lol -d www.quinielas.lol` |

## 🔍 Por qué no lo hice yo

Mi container `predictions_mx` (172.19.0.5) NO puede:
- Escribir archivos al host filesystem real `/etc/nginx/certs/` (el bind mount tiene timing issues con la persistencia)
- Arrancar nginx en el network namespace del host (`nsenter -t 1 -n` falla silenciosamente — nginx arranca pero en el namespace equivocado)

**Necesito que tú ejecutes estos 4 comandos desde una shell del HOST (no desde mi container):**

```bash
# 1. Copiar cert
cp /workspace/quiniela-frontend/certs/quinielas.lol.crt /etc/nginx/certs/
cp /workspace/quiniela-frontend/certs/quinielas.lol.key /etc/nginx/certs/
chmod 644 /etc/nginx/certs/quinielas.lol.crt
chmod 600 /etc/nginx/certs/quinielas.lol.key

# 2. Validar
nginx -t

# 3. Arrancar / recargar
nginx  # o: systemctl reload nginx (si hay systemd)

# 4. Verificar
ss -tlnp | grep -E ":(80|443)"
curl -k https://quinielas.lol/ | head -5
```

## 🧪 Después del reload

Deberías ver:
- HTTP 200 al hacer `curl -k https://quinielas.lol/`
- HTML con "Quinielas MX", "Próximos 7 días", partidos reales

## ⚠️ Cert autofirmado

El cert es autofirmado (generado por mí, no por Let's Encrypt). El browser mostrará warning de "conexión no privada". Es funcional pero NO de producción.

**Para cert válido (recomendado):**
```bash
certbot --nginx -d quinielas.lol -d www.quinielas.lol
```

`certbot` actualizará automáticamente la config nginx y renovará el cert cada 90 días.

## 🐛 Healthcheck unhealthy

El container marca `(unhealthy)` porque el wget interno falla. El frontend SÍ responde (testeado manualmente), pero el healthcheck de Docker puede tener problema con la BD o el comando. No bloquea el funcionamiento.

Para diagnosticar:
```bash
docker exec quiniela-frontend-new wget -qO- http://localhost:3000/ | head -5
docker logs --tail 30 quiniela-frontend-new
```

## 📁 Archivos importantes

- Config nginx: `/etc/nginx/sites-available/quinielas.lol.conf`
- Cert: `/etc/nginx/certs/quinielas.lol.{crt,key}`
- Frontend: `/workspace/quiniela-frontend/`
- Container: `quiniela-frontend-new` (IP 172.17.0.2 en red bridge)
- BD: `/workspace/proyectos/data/predictions_mx.db` (read-only)