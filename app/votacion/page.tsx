/**
 * /partidos — Vista principal de QUINIELA.
 *
 * Antes: hub de links a /voto/[token] (votación individual por partido).
 * Ahora: formulario batch por jornada. El usuario ve los N partidos de la
 * jornada seleccionada, toca Local/Empate/Visita para cada uno, y al final
 * hace "💾 Guardar quiniela" (un solo POST batch a /api/quiniela).
 *
 * Diseño:
 * - Jornada por defecto: la próxima que aún NO haya empezado.
 * - Selector de jornada arriba (chips horizontales).
 * - Una fila por partido con 3 botones grandes (estilo iOS).
 * - Footer sticky con botón "Guardar quiniela" + contador X/N.
 * - Si la jornada ya empezó/terminó: modo lectura (crowd bars, sin botones).
 *
 * Links individuales por partido (compat): /voto/[token] sigue funcionando
 * para quien reciba un link compartido por WhatsApp/Telegram.
 */

import Link from "next/link";
import { cookies } from "next/headers";
import {
  getUpcomingJornadas,
  getNextOpenJornada,
  getFixturesByJornadaExact,
} from "@/lib/db/fixtures";
import {
  getCrowdSummary,
} from "@/lib/db";
import { getUserPicksBatch, type Pick } from "@/lib/db/votes";
import {
  getOrCreateClientIdentity,
  CLIENT_COOKIE,
  VOTED_COOKIE,
} from "@/lib/votes/client-hash";
import { QuinielaForm } from "@/components/votes/QuinielaForm";
import { BackButton } from "@/components/layout";

export const dynamic = "force-dynamic";

interface SearchParams {
  season_id?: string;
  matchday?: string;
}

export default function PartidosPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  // 1. Listar todas las jornadas futuras para el selector
  const jornadas = getUpcomingJornadas(180);

  // 2. Determinar la jornada a mostrar:
  //    a) Si la URL tiene ?season_id=&matchday=, usar esa
  //    b) Si no, usar la próxima que NO haya empezado
  let current: { season_id: number; matchday: number; label: string } | null =
    null;

  if (searchParams.season_id && searchParams.matchday) {
    const sid = Number(searchParams.season_id);
    const md = Number(searchParams.matchday);
    const found = jornadas.find(
      (j) => j.season_id === sid && j.matchday === md,
    );
    if (found) {
      current = {
        season_id: found.season_id,
        matchday: found.matchday,
        label: `Jornada ${found.ordinal}`,
      };
    }
  }
  if (!current) {
    const next = getNextOpenJornada();
    if (next && !next.has_started) {
      current = {
        season_id: next.season_id,
        matchday: next.matchday,
        label: `Jornada ${next.ordinal}`,
      };
    } else if (next) {
      // Todas las futuras ya empezaron: mostrar la primera (modo lectura)
      current = {
        season_id: next.season_id,
        matchday: next.matchday,
        label: `Jornada ${next.ordinal}`,
      };
    }
  }

  if (!current || jornadas.length === 0) {
    return (
      <div className="space-y-6 cp-animate-up">
        <Header />
        <EmptyState />
      </div>
    );
  }

  // 3. Traer los partidos de esa jornada
  const partidosBase = getFixturesByJornadaExact(
    current.season_id,
    current.matchday,
  );

  // 4. Identidad del votante (cookie compartida con /api/votes/[token])
  //    En server component no hay NextRequest; usamos cookies() directamente.
  const cookieStore = cookies();
  const cookie = cookieStore.get(CLIENT_COOKIE)?.value;
  // Sin cookie: el votante aún no votó nada. Le pasamos hash "" y
  // el API creará la cookie al primer POST. Para getUserPicksBatch,
  // un hash vacío devuelve Map vacío.
  const identity = cookie
    ? getOrCreateClientIdentity()
    : { hash: "" };

  // 5. Picks existentes del votante para esta jornada
  const fixtureIds = partidosBase.map((f) => f.id);
  const picksMap = identity.hash
    ? getUserPicksBatch(fixtureIds, identity.hash)
    : new Map<number, Pick>();
  const initialPicks: Record<number, Pick> = {};
  for (const [fid, pick] of picksMap) initialPicks[fid] = pick;

  // 6. Crowd summaries (para mostrar % en los botones)
  const partidosConCrowd = partidosBase.map((f) => ({
    ...f,
    crowd_summary: getCrowdSummary(f.id),
  }));

  // 7. ¿La jornada ya empezó/terminó?
  const nowMs = Date.now();
  const isLocked = partidosConCrowd.every(
    (f) => new Date(f.starting_at).getTime() <= nowMs || f.home_score !== null,
  );

  // 8. ¿El usuario YA VOTÓ al menos una vez en esta sesión?
  //    Lo detectamos con una cookie simple (VOTED_COOKIE) que se setea
  //    en el POST /api/quiniela cuando un voto se guarda OK. Esto evita
  //    el problema de hash mismatch entre server component (sin IP/UA)
  //    y route handler (con IP/UA completos).
  const hasVotedBefore = cookieStore.get(VOTED_COOKIE)?.value === "1";

  // 8. Etiquetas de jornadas para el selector
  const jornadasForChips = jornadas.map((j) => ({
    season_id: j.season_id,
    matchday: j.matchday,
    label: `J${j.ordinal}`,
    first_kickoff: j.first_kickoff,
    match_count: j.match_count,
    has_started: j.has_started,
  }));

  return (
    <div className="space-y-6 cp-animate-up">
      <Header />

      <QuinielaForm
        currentJornada={current}
        jornadas={jornadasForChips}
        partidos={partidosConCrowd}
        initialPicks={initialPicks}
        hasVotedBefore={hasVotedBefore}
        isLocked={isLocked}
      />

      <Footnote />
    </div>
  );
}

// ─── Sub-componentes locales ──────────────────────────────────────────────
function Header() {
  return (
    <header style={{ paddingBottom: 4 }}>
      <BackButton href="/" label="Inicio" />
      <h1
        style={{
          fontSize: "1.5rem",
          fontWeight: 800,
          letterSpacing: "-0.02em",
          color: "var(--label-primary)",
        }}
      >
        Quiniela
      </h1>
      <p
        style={{
          fontSize: "0.875rem",
          color: "var(--label-secondary)",
          marginTop: 4,
        }}
      >
        Llena tu quiniela jornada por jornada
      </p>
    </header>
  );
}

function EmptyState() {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "40px 20px",
        background: "var(--bg-elevated)",
        border: "1px solid var(--hairline)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <p
        style={{
          fontSize: "1rem",
          fontWeight: 700,
          color: "var(--label-primary)",
        }}
      >
        No hay jornadas disponibles
      </p>
      <p
        style={{
          fontSize: "0.875rem",
          color: "var(--label-tertiary)",
          marginTop: 6,
        }}
      >
        La Liga MX está entre jornadas. Vuelve cuando se acerque la próxima fecha.
      </p>
    </div>
  );
}

function Footnote() {
  return (
    <p
      style={{
        fontSize: "0.65rem",
        color: "var(--label-tertiary)",
        textAlign: "center",
        paddingTop: 8,
        paddingBottom: 8,
      }}
    >
      1 voto por persona (cookie anti-spam) · Puedes editar mientras la jornada no empiece
    </p>
  );
}