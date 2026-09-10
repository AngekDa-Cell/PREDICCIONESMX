# Sistema de Quinielas Crowdsourced

> Documento técnico del sistema de votación de la comunidad.
> Última actualización: 2026-09-10 (Fase A.2 — sprint 4)

---

## 🎯 Visión general

El **sistema de quinielas crowdsourced** permite a cualquier visitante de [predicciones.barberia.date](https://predicciones.barberia.date) registrar sus pronósticos para los próximos partidos de la Liga MX. Los votos se agregan de forma anónima (mediante hashes) para generar **crowd summaries** que se comparan contra las predicciones del modelo.

**Tres casos de uso:**
1. **Voto individual** (`/voto/[token]`) — link compartible por partido (WhatsApp, Twitter, etc.).
2. **Quiniela batch** (`/votacion`) — llenar todos los picks de una jornada completa de una vez.
3. **Crowd summary** — % de picks de la comunidad por partido, revelados al usuario solo después de votar.

**Privacidad:** nunca guardamos IPs crudas ni UAs completos. Solo fingerprints hasheados.

---

## 🔄 Flujo end-to-end

### 1. Visitante llega a `/voto/[token]`

```
Visitante → GET /voto/ABC23XYZ
                 │
                 ├─ [token] valid? → 404 si no
                 ├─ resolveTokenAsync(token, db) → fixture_id
                 ├─ getOrCreateClientIdentity(req)
                 │    ├─ lee cookie "votante_id" o crea nueva (16 bytes hex)
                 │    ├─ lee IP prefix de X-Forwarded-For
                 │    ├─ lee User-Agent
                 │    └─ genera client_hash = sha256(cookie:sha256(votante:ip:ua))[:32]
                 │
                 └─ Renderiza VoteForm con:
                      - crowd summary (% picks de la comunidad)
                      - pick actual del usuario (si ya votó)
                      - 3 botones (Local/Empate/Visita)
```

### 2. Visitante vota

```
Visitante → POST /api/votes/[token]  body: {pick: 'home'|'draw'|'away'}
                 │
                 ├─ [token] valid? → 404 si no
                 ├─ getOrCreateClientHash(req) → {hash, createdCookie, cookie}
                 ├─ recordVote(fixtureId, clientHash, pick, ipPrefix, uaFingerprint)
                 │    ├─ INSERT OR IGNORE INTO votes (...)
                 │    ├─ si duplicate: retorna existing pick + summary
                 │    └─ actualiza vote_meta (first/last/count)
                 │
                 ├─ Set-Cookie: votante_id (HttpOnly, 180d) si createdCookie
                 ├─ Set-Cookie: votante_quinc_v1 (HttpOnly, 365d) marca "ya votó"
                 │
                 └─ Responde 200 con:
                      {ok: true, pick: 'home', summary: {home: 60%, draw: 25%, away: 15%}}
```

### 3. Visitante llena quiniela completa

```
Visitante → POST /api/quiniela  body: {jornada: {season_id, matchday}, picks: [...]}
                 │
                 ├─ Valida que TODOS los fixture_id correspondan a (season_id, matchday)
                 ├─ Valida que aún no hayan empezado (starting_at > now)
                 ├─ Valida que home_score sea null (no finalizado)
                 ├─ getOrCreateClientIdentity(req) → mismo hash que /api/votes/[token]
                 ├─ recordVotesBatch(...) → INSERT en transacción
                 │
                 └─ Responde con saved[] + summaries actualizados
```

### 4. Visitante refresca la página

```
GET /api/votes/[token] → summary + user_pick
GET /api/quiniela?season_id=&matchday= → picks del votante para la jornada
```

---

## 🗄️ Modelo de datos

### BD principal (`predictions_mx.db`)

**Solo LECTURA.** El frontend nunca escribe aquí.

### BD secundaria (`votes_mx.db`)

```sql
CREATE TABLE IF NOT EXISTS votes (
  fixture_id     INTEGER NOT NULL,
  client_hash    TEXT    NOT NULL,
  pick           TEXT    NOT NULL CHECK(pick IN ('home','draw','away')),
  ip_prefix      TEXT,
  ua_fingerprint TEXT,
  created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (fixture_id, client_hash)
);

CREATE INDEX IF NOT EXISTS idx_votes_fixture ON votes(fixture_id);
CREATE INDEX IF NOT EXISTS idx_votes_created ON votes(created_at);

CREATE TABLE IF NOT EXISTS vote_meta (
  fixture_id    INTEGER PRIMARY KEY,
  first_vote_at TEXT,
  last_vote_at  TEXT,
  vote_count    INTEGER DEFAULT 0
);
```

**Pragmas:**
- `journal_mode = WAL` (concurrencia read/write)
- `synchronous = NORMAL` (performance vs durability, OK para votos)
- `wal_autocheckpoint = 100` (auto-checkpoint cada ~400KB — crítico para no perder votos)
- `foreign_keys = ON`

**Restricción PK compuesta:** un votante (client_hash) solo puede tener UN pick por partido. Re-votar actualiza (en realidad `INSERT OR IGNORE` previene duplicados — primer voto gana, ver `lib/db/votes.ts`).

---

## 🔐 Identidad del votante

### `client_hash` (`lib/votes/client-hash.ts`)

```
client_hash = sha256(cookie + ":" + sha256("votante:" + ip_prefix + ":" + ua_fingerprint))[:32]
```

**Componentes:**

| Componente | Fuente | Privacidad |
|---|---|---|
| `cookie` | `votante_id` cookie (16 bytes hex random), creada si no existe | Anonimiza al votante entre IPs/UA |
| `ip_prefix` | Primera IP de `X-Forwarded-For` o `X-Real-IP` | Solo prefijo, NO IP completa |
| `ua_fingerprint` | Primeros 16 chars de `md5(user-agent)` | Hash unidireccional del UA |

**¿Por qué este esquema?**

1. **Anonimato:** el hash es unidireccional (no se puede revertir a cookie + IP + UA).
2. **Estabilidad:** mismo votante entre endpoints (cookie compartida entre `/api/quiniela` y `/api/votes/[token]`).
3. **Anti-flood:** votar dos veces con misma cookie/IP/UA → mismo hash → solo cuenta una vez.
4. **Sin PII:** no guardamos IPs ni UAs completos (cumplimiento RGPD-like).

### Cookies

| Cookie | Valor | Max-Age | Atributos | Propósito |
|---|---|---|---|---|
| `votante_id` | 16 bytes hex random | 180 días | HttpOnly, SameSite=Lax, Secure (prod), Path=/ | Identificador único del votante |
| `votante_quinc_v1` | `1` | 365 días | HttpOnly, SameSite=Lax, Secure (prod), Path=/ | Marca "ya votó al menos una vez" (activa revelación de % crowd) |

**Generación de cookie nueva:**
```typescript
let cookie = cookieStore.get(CLIENT_COOKIE)?.value;
let createdCookie = false;
if (!cookie) {
  cookie = crypto.randomBytes(16).toString("hex");
  createdCookie = true;
}
```

---

## 🎫 Tokens opacos

### Esquema (`lib/votes/token.ts`)

```
token = base32(sha256(SECRET_SALT + ':' + fixtureId))[:8]
```

**Propiedades:**

- **8 caracteres base32** (A-Z2-7 sin ambiguos 0/O/1/I/L) — 32^8 = ~1 billón de combinaciones.
- **Determinístico:** misma entrada → mismo token (no requiere lookup en BD para generar).
- **Anti-enumeración:** requiere `SECRET_SALT` para precomputar tokens de partidos no publicados.
- **No expone `fixture_id`** directamente en la URL.
- **Lookup O(1)** con caché en memoria (TTL 5 min).

### Flujo de resolución

```
GET /voto/ABC23XYZ
  ├─ isValidToken('ABC23XYZ')?  → regex /^[A-HJ-NP-Z2-9]{8}$/
  ├─ resolveTokenAsync(token, db)
  │    ├─ cache hit? → return fixture_id (O(1))
  │    └─ cache miss:
  │         ├─ loadTokenIndex(db):
  │         │    SELECT id FROM fixtures WHERE league_id=743
  │         │    for each row: map[makeToken(id)] = id
  │         └─ cache for 5 min
  └─ return fixture_id (404 si no encontrado)
```

### Configuración del salt

```typescript
function getSalt(): string {
  return process.env.VOTES_TOKEN_SALT || "quinielas-lol-default-salt";
}
```

⚠️ **IMPORTANTE:** cambiar `VOTES_TOKEN_SALT` en producción (Dokploy secret). Si no, todos los tokens son predecibles.

---

## 📊 Crowd Summary

### Cálculo (`lib/db/votes.ts` → `getCrowdSummary`)

```typescript
function getCrowdSummary(fixtureId: number): CrowdSummary {
  const rows = db.prepare(`
    SELECT pick, COUNT(*) as n
    FROM votes
    WHERE fixture_id = ?
    GROUP BY pick
  `).all(fixtureId);
  
  const total = rows.reduce((s, r) => s + r.n, 0);
  return {
    total,
    breakdown: {
      home: (rows.find(r => r.pick === 'home')?.n ?? 0) / total,
      draw: (rows.find(r => r.pick === 'draw')?.n ?? 0) / total,
      away: (rows.find(r => r.pick === 'away')?.n ?? 0) / total,
    },
    asOf: new Date().toISOString(),
  };
}
```

**Ejemplo de respuesta:**
```json
{
  "total": 23,
  "breakdown": {
    "home": 0.609,
    "draw": 0.217,
    "away": 0.174
  },
  "asOf": "2026-09-10T18:23:11.456Z"
}
```

### Cuándo se revela

- **ANTES de votar:** NO se muestra el crowd summary (incentivo a votar sin anclaje).
- **DESPUÉS de votar:** cookie `votante_quinc_v1=1` activa la revelación en `/votacion` y `/voto/[token]`.

**Mecanismo:**
```typescript
// Server component
const voted = cookieStore.get(VOTED_COOKIE)?.value === "1";
return <CrowdSummary summary={summary} visible={voted} />;
```

---

## 🛡️ Validación y seguridad

### Anti-SQLi (`lib/validation.ts`)

**TODOS los IDs de URL** se validan con regex `^\d{1,10}$`:

```typescript
export function validateFixtureId(id: string | undefined): number | null {
  if (!id) return null;
  if (!/^\d{1,10}$/.test(id)) return null;
  const n = parseInt(id, 10);
  if (isNaN(n) || n <= 0) return null;
  return n;
}
```

**Aplicado en:**
- `app/partido/[id]/page.tsx`
- `app/equipo/[id]/page.tsx`
- `app/voto/[token]/page.tsx`
- `app/api/votes/[token]/route.ts`
- `app/api/quiniela/route.ts`

### Validación de picks

```typescript
if (typeof body.pick !== "string" || !["home", "draw", "away"].includes(body.pick)) {
  return NextResponse.json({ error: "invalid_pick" }, { status: 400 });
}
```

### Validación de jornada (batch)

```typescript
// Verificar que TODOS los fixture_id correspondan a (season_id, matchday)
// y que aún no hayan empezado (starting_at > now)
// y que home_score sea null (no finalizado)
```

### Queries parametrizadas

Todas las queries usan placeholders `?`, NUNCA interpolación de strings:

```typescript
// ✅ CORRECTO
db.prepare(`SELECT * FROM fixtures WHERE id = ?`).all(fixtureId);

// ❌ INCORRECTO (nunca usado en este proyecto)
db.prepare(`SELECT * FROM fixtures WHERE id = ${fixtureId}`).all();
```

---

## 📈 Métricas y monitoreo

### Métricas live

- **Votos totales:** ~10/día (creciendo)
- **Votantes únicos (client_hash):** ~50/mes
- **Tasa de re-voto:** <5%
- **Crowd summary hit rate:** >80% (la mayoría vota y refresca)

### Anti-abuso

- **Flood protection:** PK compuesta `(fixture_id, client_hash)` previene duplicados por votante.
- **Hash collision:** 32 chars hex (128 bits) → probabilidad de colisión negligible.
- **Sin rate limiting explícito:** confiamos en que votar es barato y no hay incentivo económico directo.

### Monitoreo pendiente (Fase D.3)

- [ ] Métricas Prometheus (votos/min, errores 4xx/5xx, latencia)
- [ ] Alertas si votes_mx.db crece >100MB
- [ ] Dashboard de crowd vs modelo

---

## 🔌 API Reference

### `POST /api/votes/[token]`

Registra voto individual para un partido.

**Request:**
```json
POST /api/votes/ABC23XYZ
Content-Type: application/json

{ "pick": "home" }
```

**Response 200:**
```json
{
  "ok": true,
  "already_voted": false,
  "pick": "home",
  "summary": {
    "total": 23,
    "breakdown": { "home": 0.609, "draw": 0.217, "away": 0.174 },
    "asOf": "2026-09-10T18:23:11.456Z"
  }
}
```

**Errores:**
- `400 invalid_json` — body no parseable
- `400 invalid_pick` — pick no es home/draw/away
- `404 invalid_token` — token no pasa regex
- `404 not_found` — token válido pero sin fixture asociado

**Cookies de response:**
- `votante_id` (si no existía) — HttpOnly, 180d
- `votante_quinc_v1=1` — marca "ya votó"

---

### `GET /api/votes/[token]`

Trae crowd summary + pick actual del votante.

**Response 200:**
```json
{
  "ok": true,
  "fixture_id": 12345,
  "summary": { ... },
  "user_pick": "home"
}
```

---

### `POST /api/quiniela`

Guarda batch de picks por jornada completa.

**Request:**
```json
POST /api/quiniela
Content-Type: application/json

{
  "jornada": { "season_id": 1, "matchday": 12 },
  "picks": [
    { "fixture_id": 12345, "pick": "home" },
    { "fixture_id": 12346, "pick": "draw" },
    { "fixture_id": 12347, "pick": "away" }
  ]
}
```

**Response 200:**
```json
{
  "ok": true,
  "saved": [
    { "fixture_id": 12345, "pick": "home", "status": "inserted" },
    { "fixture_id": 12346, "pick": "draw", "status": "inserted" },
    { "fixture_id": 12347, "pick": "away", "status": "duplicate" }
  ],
  "summaries": { "12345": { ... }, ... }
}
```

**Errores:**
- `400 invalid_jornada` — season_id o matchday inválidos
- `400 missing_picks` — picks no es array
- `400 fixture_jornada_mismatch` — fixture no corresponde a la jornada
- `400 fixture_already_started` — partido ya empezó
- `400 fixture_already_finished` — partido finalizado

---

### `GET /api/quiniela?season_id=&matchday=[&summaries=1]`

Trae picks del votante para una jornada.

**Response 200:**
```json
{
  "ok": true,
  "picks": { "12345": "home", "12346": "draw" },
  "summaries": { "12345": { ... } }  // si summaries=1
}
```

---

## 🧪 Testing

### Manual

```bash
# Voto individual
curl -X POST https://predicciones.barberia.date/api/votes/ABC23XYZ \
  -H "Content-Type: application/json" \
  -d '{"pick": "home"}' \
  -c cookies.txt

# Crowd summary
curl https://predicciones.barberia.date/api/votes/ABC23XYZ -b cookies.txt

# Batch
curl -X POST https://predicciones.barberia.date/api/quiniela \
  -H "Content-Type: application/json" \
  -d '{"jornada":{"season_id":1,"matchday":12},"picks":[{"fixture_id":12345,"pick":"home"}]}' \
  -b cookies.txt -c cookies.txt
```

### Pendiente

- [ ] Tests E2E con Playwright (flujo completo de voto)
- [ ] Tests unitarios de `lib/votes/*` (token, hash, validation)
- [ ] Tests de concurrencia (100 votos simultáneos al mismo fixture)

---

## 📚 Ver también

- [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) — arquitectura general del frontend
- [`docs/DEPLOY_DOKPLOY.md`](./DEPLOY_DOKPLOY.md) — deploy Dokploy
- `lib/votes/token.ts` — implementación de tokens opacos
- `lib/votes/client-hash.ts` — implementación de client_hash
- `lib/validation.ts` — regex anti-SQLi
- `lib/db/votes.ts` — queries de votos
- `app/api/votes/[token]/route.ts` — endpoint voto individual
- `app/api/quiniela/route.ts` — endpoint batch
