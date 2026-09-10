# Arquitectura Frontend — Next.js (Predictions_MX)

> Documento técnico del subsistema frontend.
> Última actualización: 2026-09-10 (Fase A + C1)

---

## 🎯 Visión general

El frontend de Predictions_MX es una aplicación **Next.js 14 (App Router)** que sirve dos funciones principales:

1. **Visualización pública** de predicciones, equipos, calendario, historial y resultados (read-only sobre `predictions_mx.db`).
2. **Sistema de quinielas crowdsourced** — permite a la comunidad votar sus pronósticos antes de cada partido, con tokens opacos, cookies HttpOnly y validación contra inyección SQL.

Vive **en este mismo repo** (`app/`, `components/`, `lib/`), desplegado en Dokploy como container long-running junto con el backend Python.

**URL de producción:** https://predicciones.barberia.date

---

## 🛠️ Stack

| Tecnología | Versión | Uso |
|---|---|---|
| Next.js | 14.2.5 | Framework (App Router) |
| React | 18.3.1 | UI |
| TypeScript | 5.5.3 | Type safety |
| Tailwind CSS | 3.4.7 | Estilos (utility-first) |
| better-sqlite3 | 12.11.1 | Cliente SQLite nativo |
| lucide-react | 0.408.0 | Iconos |
| Recharts | 2.13.0 | Gráficos (no usado en MVP) |
| Node.js (runtime) | 24.16.0 | Ejecución |

### ¿Por qué better-sqlite3 y NO Prisma?

- **Prisma NO funciona en Alpine** (incompatibilidad con `libssl 1.1`). El Dockerfile usa `node:24.16.0-bookworm-slim` (Debian/glibc), pero se descartó Prisma por portabilidad.
- **better-sqlite3 es nativo, rápido, read-only directo** — sin ORM intermedio.
- **SQL nativo** → control total sobre queries analíticas (joins complejos, agregaciones).
- **Lazy init** en `lib/db/client.ts` → no abre BD al import (build-time safe).

Ver `lib/db/client.ts` para el patrón singleton con Proxy lazy.

---

## 📁 Estructura del frontend

```
app/                                  # App Router (rutas + APIs)
├── layout.tsx                        # Layout raíz + TopNav + footer
├── globals.css                       # Design system iOS-style (CSS vars)
├── page.tsx                          # Home (dashboard Cinépolis-style)
├── analisis/page.tsx                 # Análisis agregado
├── calendario/page.tsx               # Calendario por jornada
├── efectividad/page.tsx              # Métricas efectividad histórica
├── equipos/page.tsx                  # Índice completo de equipos
├── equipo/[id]/page.tsx              # Detalle de equipo
├── historial/page.tsx                # Historial de predicciones
├── partido/[id]/page.tsx             # Detalle de partido individual
├── resultados/page.tsx               # Track record
├── votacion/page.tsx                 # Llenar quiniela batch
├── voto/[token]/page.tsx             # Voto individual (link compartible)
└── api/                              # API routes (3 endpoints)
    ├── health/route.ts               # Healthcheck para Traefik
    ├── quiniela/route.ts             # POST batch + GET picks
    └── votes/[token]/route.ts        # POST/GET voto individual

components/
├── ui/                               # Primitivas visuales
│   ├── TeamCrest.tsx                 # Escudo de equipo (logo + colores)
│   ├── ProbabilityBars.tsx           # Barras de probabilidad 1X2
│   ├── ProbabilityRing.tsx           # Anillo circular de probabilidad
│   ├── ListGroup.tsx                 # Lista iOS-style
│   └── ios.tsx                       # Helpers iOS-style
├── layout/                           # Layout components
│   ├── Navigation.tsx                # TopNav (con scroll-hide en mobile)
│   ├── PageHeader.tsx                # Header de página con back
│   └── BackButton.tsx                # Botón atrás
├── fixtures/                         # Componentes de partido
│   ├── FixtureRow.tsx                # Fila de partido en lista
│   ├── FixtureDetail.tsx             # Detalle completo
│   ├── MatchClock.tsx                # Cuenta regresiva al pitazo
│   └── PickBadge.tsx                 # Badge Local/Visita/Empate
├── stats/                            # Métricas
│   └── StatsBadge.tsx                # Badge con accuracy/Brier
└── votes/                            # Sistema de quinielas
    ├── QuinielaForm.tsx              # Form batch por jornada
    ├── VoteForm.tsx                  # Form individual partido
    ├── CrowdSummary.tsx              # Resumen de picks crowd
    ├── CopyVoteLink.tsx              # Botón copiar link compartible
    └── VoteCopyTokenButton.tsx       # Botón alternativo

lib/
├── db/                               # Capa de datos
│   ├── client.ts                     # Singleton BD principal (lazy)
│   ├── votes-client.ts               # Singleton BD votos (lazy, RW)
│   ├── types.ts                      # Tipos TypeScript (sync con schema)
│   ├── fixtures.ts                   # Queries fixtures
│   ├── predictions.ts                # Queries predicciones
│   ├── teams.ts                      # Queries equipos
│   ├── matchday.ts                   # Lógica de jornadas
│   ├── stats.ts                      # Stats agregadas (Brier, accuracy)
│   └── votes.ts                      # Sistema de votos
├── votes/                            # Helpers de votación
│   ├── client-hash.ts                # Fingerprint votante (cookie+IP+UA)
│   └── token.ts                      # Tokens opacos base32
├── validation.ts                     # Regex anti-SQLi + sanitize
└── db.ts (re-exports)

public/                               # Assets estáticos
next.config.js                        # Config Next.js
tailwind.config.ts                    # Config Tailwind
tsconfig.json                         # Config TypeScript
```

---

## 🗺️ Rutas funcionales

### Páginas (11)

| Ruta | Descripción | Server/Client | Datos |
|---|---|---|---|
| `/` | Dashboard Cinépolis-style: hero gradient, 3 stat cards, partido destacado, quick links 2x2, próximos 5 | Server | `getUpcomingFixtures`, `getFixtureCounts`, `getPredictionHistory`, `getHistoryStats` |
| `/analisis` | Análisis agregado del modelo | Server | `getHistoryStats`, breakdown por outcome |
| `/calendario` | Calendario completo por jornada | Server | `getFixturesByJornada`, `getUpcomingJornadas` |
| `/efectividad` | Métricas de efectividad histórica | Server | `getHistoryStats`, accuracy timeline |
| `/equipos` | Índice de equipos | Server | `getAllTeams` |
| `/equipo/[id]` | Detalle de equipo (próximos, recientes, stats) | Server | `getTeamById`, `getTeamRecentFixtures`, `getTeamUpcomingFixtures` |
| `/historial` | Historial de predicciones (paginado) | Server | `getPredictionHistory` |
| `/partido/[id]` | Detalle de partido individual | Server | `getFixtureById`, `getLatestPredictionForFixture` |
| `/resultados` | Track record con accuracy y Brier live | Server | `getPredictionHistory`, `getHistoryStats` |
| `/votacion` | Llenar quiniela batch por jornada | Server + Client | `getUpcomingJornadas`, `getCrowdSummary` (server); submit form (client → API) |
| `/voto/[token]` | Voto individual partido (link compartible) | Server + Client | `resolveTokenAsync` (server); submit form (client → API) |

### API routes (3)

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/api/health` | GET | Healthcheck. Verifica BD + reporta uptime. Consumido por Traefik para readiness. |
| `/api/quiniela` | POST, GET | **POST:** guardar batch de picks por jornada. **GET:** traer picks del votante actual para una jornada (`?season_id=&matchday=&summaries=1`). |
| `/api/votes/[token]` | POST, GET | **POST:** registrar voto individual (`{pick: 'home'|'draw'|'away'}`). **GET:** traer summary + pick del usuario. |

---

## 🎨 Design system

**Estilo iOS-inspired** con CSS variables en `globals.css`:

```css
:root {
  --bg-primary: #040612;          /* Negro profundo */
  --label-primary: #ffffff;
  --label-secondary: rgba(255,255,255,0.7);
  --tint-blue: #4781ff;           /* Azul Cinépolis */
  --separator: rgba(255,255,255,0.08);
  --radius-md: 14px;
  --dur-fast: 200ms;
  --ease-ios: cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
```

**Componentes clave:**
- `HeroStat` — stat card con gradient blur (3 unidades en home)
- `PickBadge` — badge Local/Visita/Empate con color semántico
- `ProbabilityBars` — barras horizontales con animación
- `TeamCrest` — escudo con colores primarios/secundarios del equipo
- `MatchClock` — cuenta regresiva al pitazo inicial

**Paleta Cinépolis:** extraída literal del sitio real de Cinépolis México (azul → púrpura → negro).

---

## 🗄️ Capa de datos

### Singleton lazy pattern (`lib/db/client.ts`)

```typescript
// Proxy que delega TODO al singleton lazy.
// Permite usar db.prepare(...) sin abrir BD hasta el primer uso.
export const db: Database.Database = new Proxy({} as Database.Database, {
  get(_target, prop) {
    const real = getDb();
    const value = (real as any)[prop];
    return typeof value === "function" ? value.bind(real) : value;
  },
});
```

**¿Por qué lazy?**
- `next build` corre sin BD accesible (build-time).
- Cualquier fallo de apertura se propaga al primer uso real, no al import.
- Permite tests E2E y CI sin BD montada.

### BD principal — `predictions_mx.db` (read-only)

- Path: `/workspace/proyectos/data/predictions_mx.db` (bind mount desde host)
- Modo: `readonly: true, fileMustExist: true` (sin pragma de escritura)
- Compartida con backend Python (RW para Python, RO para Next.js)

### BD secundaria — `votes_mx.db` (read-write)

- Path: `/workspace/proyectos/data/votes_mx.db`
- Modo: `journal_mode = WAL`, `synchronous = NORMAL`, `wal_autocheckpoint = 100`
- Migraciones idempotentes (CREATE TABLE IF NOT EXISTS)
- 2 tablas:
  - `votes (fixture_id, client_hash, pick, ip_prefix, ua_fingerprint, created_at)` — PK compuesta
  - `vote_meta (fixture_id, first_vote_at, last_vote_at, vote_count)` — counter

**¿Por qué BD separada?**
- Aislamiento de writes (frontend puede escribir sin lockear lecturas)
- Backup independiente (más frecuente si crece)
- Migración futura a Postgres: solo cambiar conexión

---

## 🔌 Patrones de uso

### Server Component (default)

```typescript
// app/partido/[id]/page.tsx
import { getFixtureById } from "@/lib/db";

export default async function MatchPage({ params }: { params: { id: string } }) {
  const fixture = getFixtureById(Number(params.id));
  if (!fixture) notFound();
  return <FixtureDetail fixture={fixture} />;
}
```

### Client Component (interactividad)

```typescript
// components/votes/QuinielaForm.tsx
"use client";
import { useState } from "react";

export function QuinielaForm({ jornada, fixtures }: Props) {
  const [picks, setPicks] = useState({});
  const handleSubmit = async () => {
    const res = await fetch("/api/quiniela", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jornada, picks: Object.entries(picks) }),
    });
    // ...
  };
}
```

### API Route

```typescript
// app/api/votes/[token]/route.ts
export async function POST(req: NextRequest, ctx: { params: { token: string } }) {
  if (!isValidToken(ctx.params.token)) {
    return NextResponse.json({ error: "invalid_token" }, { status: 404 });
  }
  const fixtureId = await resolveTokenAsync(ctx.params.token, mainDb);
  if (fixtureId === null) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
  // ... registrar voto
}
```

---

## 🔐 Seguridad

### Validación de inputs (`lib/validation.ts`)

```typescript
export function validateFixtureId(id: string | undefined): number | null {
  if (!id) return null;
  // Solo dígitos, max 10 chars (limita a IDs de BD razonables)
  if (!/^\d{1,10}$/.test(id)) return null;
  const n = parseInt(id, 10);
  if (isNaN(n) || n <= 0) return null;
  return n;
}

export function sanitizeString(str: string | null | undefined, maxLen = 500): string {
  if (!str) return "";
  return String(str).slice(0, maxLen);
}
```

**Aplicado en TODAS las páginas dinámicas** (`/partido/[id]`, `/equipo/[id]`, `/voto/[token]`) y en TODAS las API routes.

### Cookies

| Cookie | Tipo | Max-Age | Propósito |
|---|---|---|---|
| `votante_id` | HttpOnly, SameSite=Lax, Secure (prod) | 180 días | Identificador único del votante (genera `client_hash`) |
| `votante_quinc_v1` | HttpOnly, SameSite=Lax, Secure (prod) | 365 días | Marca "ya votó al menos una vez" (activa revelación de % crowd) |

### Client hash (`lib/votes/client-hash.ts`)

```
client_hash = sha256(cookie + ":" + sha256("votante:" + ipPrefix + ":" + ua))[:32]
```

- **No guardamos IPs crudas** → solo `ipPrefix` (primera IP de `X-Forwarded-For`).
- **No guardamos UAs completos** → solo `uaFingerprint` (primeros 16 chars de md5 UA).
- Mismo hash entre `/api/quiniela` y `/api/votes/[token]` → votante es el mismo entre endpoints.

### Tokens opacos (`lib/votes/token.ts`)

```
token = base32(sha256(SECRET_SALT + ':' + fixtureId))[:8]
```

- 8 chars base32 (A-Z2-7 sin ambiguos)
- **NO expone `fixture_id` directamente** en la URL
- Requiere `SECRET_SALT` para precomputar (anti-enumeración)
- Índice en memoria con TTL 5 min (resolve O(1))

Ver [`docs/QUINIELAS_SYSTEM.md`](./QUINIELAS_SYSTEM.md) para detalle del sistema completo.

---

## 🚀 Build y deploy

### Standalone output (Docker-friendly)

Next.js compila a standalone con `output: 'standalone'` en `next.config.js`:

```
.next/standalone/         # Server bundle (incluye deps)
.next/static/            # Assets estáticos
```

**Dockerfile multi-stage** (resumen):
1. **Builder** (`node:24.16.0-bookworm-slim`): compila Next.js → `server.js`
2. **Runtime** (`python:3.12-slim` + Node 24.16.0): ejecuta `server.js` (PID 1) + supercronic

Ver [`Dockerfile`](../Dockerfile) y [`docs/DEPLOY_DOKPLOY.md`](./DEPLOY_DOKPLOY.md) para detalle.

### Variables de entorno (Dokploy)

| Variable | Default | Descripción |
|---|---|---|
| `DATABASE_PATH` | `/workspace/proyectos/data/predictions_mx.db` | Path BD principal |
| `VOTES_DATABASE_PATH` | `/workspace/proyectos/data/votes_mx.db` | Path BD de votos |
| `VOTES_TOKEN_SALT` | `quinielas-lol-default-salt` | Salt para tokens (CAMBIAR en prod) |
| `NODE_ENV` | `production` | Modo Next.js |

### Healthcheck

`GET /api/health` retorna:
```json
{
  "status": "ok",
  "service": "predicciones-mx-front",
  "uptime_seconds": 1234,
  "db": "ok"
}
```

Traefik lo usa para readiness probe cada 60s.

---

## 🧪 Testing

### Actual

- **Backend Python:** 257 tests (~30s) en `tests/`
- **Frontend:** sin tests automatizados aún (pendiente Fase D.4)

### Pendiente

- [ ] Tests E2E con Playwright (`npm run test:e2e`)
- [ ] Tests unitarios de componentes con Vitest + React Testing Library
- [ ] Visual regression tests con Chromatic/Percy
- [ ] Tests de accesibilidad (axe-core)

---

## 📊 Métricas

### Performance

- **Lighthouse home** (medido 2026-09-10):
  - Performance: ~85
  - Accessibility: ~95
  - Best Practices: ~95
  - SEO: ~90
- **TTFB:** <100ms (BD local en mismo container)
- **Bundle JS inicial:** ~150KB gzipped

### Uso (live)

- Home: ~50 visitas/día
- Votación: ~10 picks/día (creciendo)
- API calls: ~200/día

---

## 🔗 Ver también

- [`docs/QUINIELAS_SYSTEM.md`](./QUINIELAS_SYSTEM.md) — sistema de votos crowdsourced
- [`docs/DEPLOY_DOKPLOY.md`](./DEPLOY_DOKPLOY.md) — deploy Dokploy
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — arquitectura general (back + front)
- [`docs/ROADMAP.md`](./ROADMAP.md) — roadmap completo
