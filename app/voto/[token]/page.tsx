/**
 * /voto/[token] — Página pública de votación.
 *
 * - Mobile-first (clientes la abren en el celular desde WhatsApp/Telegram)
 * - 3 botones: Local / Empate / Visita
 * - 1 voto por cookie+IP hash, sin login
 * - Si el partido ya empezó/terminó: muestra resumen y deshabilita voto
 *
 * Diseño iOS-style consistente con el resto del frontend.
 */

import { notFound } from "next/navigation";
import Link from "next/link";
import { cookies } from "next/headers";
import { db as mainDb } from "@/lib/db/client";
import { isValidToken, resolveTokenAsync } from "@/lib/votes/token";
import {
  getCrowdSummary,
  getUserPick,
} from "@/lib/db/votes";
import { VoteForm } from "@/components/votes/VoteForm";
import crypto from "crypto";

interface Props {
  params: { token: string };
}

const CLIENT_COOKIE = "votante_id";

function hashClientId(opts: { ipPrefix?: string; ua?: string }): string {
  const h = crypto.createHash("sha256");
  h.update("votante:");
  if (opts.ipPrefix) h.update(opts.ipPrefix);
  if (opts.ua) h.update(opts.ua);
  return h.digest("hex").slice(0, 32);
}

export async function generateMetadata({ params }: Props) {
  return {
    title: `Voto · Quinielas.lol`,
    description: "Vota Local / Empate / Visita para este partido de Liga MX",
    robots: "noindex, nofollow",
  };
}

export default async function VotoPage({ params }: Props) {
  const { token } = params;
  if (!isValidToken(token)) notFound();

  const fixtureId = await resolveTokenAsync(token, mainDb);
  if (fixtureId === null) notFound();

  // Traer info mínima del partido (server-side, BD principal readonly)
  const fixture = mainDb
    .prepare(
      `SELECT f.id, f.home_team_id, f.away_team_id, f.starting_at, f.state,
              f.home_score, f.away_score,
              ht.short_code AS home_short, ht.name AS home_name,
              at.short_code AS away_short, at.name AS away_name
       FROM fixtures f
       JOIN teams ht ON ht.id = f.home_team_id
       JOIN teams at ON at.id = f.away_team_id
       WHERE f.id = ?`,
    )
    .get(fixtureId) as {
      id: number;
      home_team_id: number;
      away_team_id: number;
      starting_at: string;
      state: string | null;
      home_score: number | null;
      away_score: number | null;
      home_short: string | null;
      home_name: string;
      away_short: string | null;
      away_name: string;
    };

  if (!fixture) notFound();

  // Determinar si se puede votar
  const startMs = new Date(fixture.starting_at).getTime();
  const nowMs = Date.now();
  const hasStarted = startMs <= nowMs;
  const isFinished =
    fixture.home_score !== null && fixture.away_score !== null;
  const canVote = !hasStarted && !isFinished;

  let notVotingReason: string | undefined;
  if (isFinished) notVotingReason = "El partido ya terminó";
  else if (hasStarted) notVotingReason = "El partido ya empezó";

  // Calcular client_hash de forma consistente con el API
  const cookieStore = cookies();
  const cookie = cookieStore.get(CLIENT_COOKIE)?.value || "";
  // En server component no tenemos ip/UA del request directo, así que usamos
  // un sub-hash solo con la cookie (degradación segura: aún anti-spam básico).
  // La API sí considera ip+UA. Cuando el cliente cargue el componente y vote,
  // se recalculará con ip+UA y se insertará con ese hash. Si difiere del preview,
  // el primer voto "reclama" la slot.
  const envHash = hashClientId({}); // sin datos del request
  const finalHash = crypto
    .createHash("sha256")
    .update(cookie + ":" + envHash)
    .digest("hex")
    .slice(0, 32);

  const summary = getCrowdSummary(fixtureId);
  const userPick = getUserPick(fixtureId, finalHash);

  const matchDateStr = new Date(fixture.starting_at).toLocaleDateString(
    "es-MX",
    {
      weekday: "long",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    },
  );

  return (
    <main
      className="min-h-screen"
      style={{ background: "var(--bg-grouped-secondary)" }}
    >
      <div className="max-w-md mx-auto px-4 py-6 space-y-4">
        {/* ─── Header ─── */}
        <header className="flex items-center justify-between">
          <Link
            href="/"
            className="ios-footnote font-semibold"
            style={{ color: "var(--tint-blue)", textDecoration: "none" }}
          >
            ← Quinielas.lol
          </Link>
          <span
            className="ios-footnote font-semibold"
            style={{ color: "var(--label-tertiary)" }}
          >
            {canVote ? "Votación abierta" : "Votación cerrada"}
          </span>
        </header>

        <VoteForm
          token={token}
          initialSummary={summary}
          initialUserPick={userPick}
          homeTeamShort={fixture.home_short || fixture.home_name.slice(0, 4).toUpperCase()}
          awayTeamShort={fixture.away_short || fixture.away_name.slice(0, 4).toUpperCase()}
          matchDate={matchDateStr}
          canVote={canVote}
          notVotingReason={notVotingReason}
        />
      </div>
    </main>
  );
}

export const dynamic = "force-dynamic";
