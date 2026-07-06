/**
 * Home — Dashboard Cinépolis-style
 *
 * Estructura:
 * 1. Hero con gradiente radial (azul→púrpura→negro) — banner de jornada
 * 2. 3 stat cards (próximos, predicciones, racha)
 * 3. Partido destacado (card grande)
 * 4. QuickLinks 2x2
 * 5. Próximos 5 partidos en lista
 *
 * Paleta Cinépolis extraída literal del sitio real.
 */
import Link from "next/link";
import {
  getUpcomingFixtures,
  getFixtureCounts,
  getPredictionHistory,
  getHistoryStats,
} from "@/lib/db";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { PickBadge } from "@/components/fixtures/PickBadge";
import { MatchClock } from "@/components/fixtures/MatchClock";

export const dynamic = "force-dynamic";

const PICK_LABEL: Record<string, string> = {
  home_win: "Local",
  away_win: "Visita",
  draw: "Empate",
};

export default function HomePage() {
  const upcoming = getUpcomingFixtures(30, 10);
  const counts = getFixtureCounts();
  const history = getPredictionHistory();
  const stats = getHistoryStats(history);

  const featured =
    upcoming.find((f) => f.prediction?.confidence !== null) ?? upcoming[0];

  const next5 = upcoming
    .filter((f) => f.id !== featured?.id)
    .slice(0, 5);

  // Stats para el hero (3 columnas)
  const upcomingCount = counts.upcoming;
  const winRate =
    stats.finished > 0
      ? Math.round((stats.hits / stats.finished) * 100)
      : null;
  const currentStreak =
    stats.current_streak.length > 0 ? `${stats.current_streak.length}` : "—";

  return (
    <div className="space-y-6 cp-animate-up">
      {/* ═══ HERO con gradiente Cinépolis ═══ */}
      <section className="cp-hero" style={{ padding: "32px 24px 28px" }}>
        <span className="cp-pill">⚽ JORNADA 1 · LIGA MX</span>
        <h1
          style={{
            marginTop: 14,
            fontSize: "1.875rem",
            fontWeight: 900,
            letterSpacing: "-0.025em",
            lineHeight: 1.05,
            color: "white",
          }}
        >
          Quiniela
          <br />
          MX
        </h1>
        <p
          style={{
            fontSize: "0.875rem",
            color: "rgba(255,255,255,0.75)",
            marginTop: 8,
            marginBottom: 18,
            fontWeight: 500,
          }}
        >
          Predicciones Liga MX con datos en vivo
        </p>

        {/* Stat cards 3 columnas dentro del hero */}
        <div className="grid grid-cols-3 gap-2">
          <HeroStat number={upcomingCount} label="Próximos" />
          <HeroStat
            number={winRate !== null ? `${winRate}%` : "—"}
            label="Efectividad"
          />
          <HeroStat number={currentStreak} label="Racha" />
        </div>
      </section>

      {/* ═══ Featured match (partido destacado) ═══ */}
      {featured ? (
        <section>
          <SectionTitle>Partido destacado</SectionTitle>
          <FeaturedMatch fixture={featured} />
        </section>
      ) : (
        <EmptyState
          title="No hay partidos próximos"
          subtitle="La Liga MX está en receso. Vuelve cuando empiece la próxima jornada."
        />
      )}

      {/* ═══ Quick links 2x2 ═══ */}
      <section>
        <div className="grid grid-cols-2 gap-3">
          <QuickLink
            href="/votacion"
            label="Ver todos"
            sub={`${counts.upcoming} próximos`}
          />
          <QuickLink
            href="/resultados"
            label="Track record"
            sub={`${stats.finished} evaluados`}
          />
          <QuickLink href="/calendario" label="Calendario" sub="Por jornada" />
          <QuickLink href="/equipos" label="Equipos" sub="Índice completo" />
        </div>
      </section>

      {/* ═══ Próximos 5 partidos ═══ */}
      {next5.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <SectionTitle inline>Próximos partidos</SectionTitle>
            <Link
              href="/votacion"
              style={{ color: "var(--tint-blue)", fontWeight: 600, fontSize: "0.75rem" }}
            >
              Ver todos →
            </Link>
          </div>

          <div
            className="cp-stat-card"
            style={{
              padding: 0,
              borderRadius: "var(--radius-md)",
              overflow: "hidden",
            }}
          >
            {next5.map((f, i) => {
              const pred = f.prediction;
              return (
                <Link
                  key={f.id}
                  href={`/partido/${f.id}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "14px 14px",
                    transition: "background-color var(--dur-fast) var(--ease-ios)",
                  }}
                  className="cp-list-row"
                >
                  {i > 0 && (
                    <span
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 14,
                        right: 14,
                        height: 1,
                        background: "var(--separator)",
                      }}
                    />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p
                      style={{
                        color: "var(--label-primary)",
                        fontWeight: 600,
                        fontSize: "0.875rem",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {f.home_team_name}
                      <span
                        style={{
                          color: "var(--tint-blue)",
                          margin: "0 6px",
                          fontWeight: 700,
                        }}
                      >
                        vs
                      </span>
                      {f.away_team_name}
                    </p>
                  </div>
                  {pred?.predicted_outcome ? (
                    <PickBadge outcome={pred.predicted_outcome} size="sm" />
                  ) : (
                    <span
                      style={{
                        color: "var(--label-tertiary)",
                        fontSize: "0.75rem",
                      }}
                    >
                      —
                    </span>
                  )}
                  <MatchClock
                    startingAt={f.starting_at}
                    status={f.state}
                    compact
                  />
                </Link>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

// ─── Hero stat card (mini stat dentro del hero gradient) ────────────────
function HeroStat({ number, label }: { number: string | number; label: string }) {
  return (
    <div
      style={{
        background: "rgba(0,0,0,0.20)",
        borderRadius: "var(--radius-md)",
        padding: "10px 8px",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div
        className="cp-text-gradient"
        style={{
          fontSize: "1.5rem",
          fontWeight: 900,
          lineHeight: 1,
          letterSpacing: "-0.02em",
        }}
      >
        {number}
      </div>
      <div
        style={{
          fontSize: "0.6rem",
          color: "rgba(255,255,255,0.7)",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.5px",
          marginTop: 4,
        }}
      >
        {label}
      </div>
    </div>
  );
}

// ─── Section title ──────────────────────────────────────────────────────
function SectionTitle({
  children,
  inline,
}: {
  children: React.ReactNode;
  inline?: boolean;
}) {
  return (
    <h2
      style={{
        fontSize: inline ? "0.75rem" : "1rem",
        fontWeight: 700,
        letterSpacing: inline ? "0.5px" : "-0.01em",
        textTransform: inline ? "uppercase" : "none",
        color: inline ? "var(--label-tertiary)" : "var(--label-primary)",
        margin: inline ? "0" : "0 0 14px",
      }}
    >
      {children}
    </h2>
  );
}

// ─── Featured match (gran card de partido destacado) ─────────────────────
function FeaturedMatch({
  fixture,
}: {
  fixture: ReturnType<typeof getUpcomingFixtures>[0];
}) {
  const f = fixture;
  const p = f.prediction;
  const isFinished = f.home_score !== null && f.away_score !== null;
  const pickLabel = p?.predicted_outcome
    ? PICK_LABEL[p.predicted_outcome] ?? p.predicted_outcome
    : null;

  return (
    <Link href={`/partido/${f.id}`} className="block ios-card ios-card-hover" style={{ padding: "20px" }}>
      <div className="flex items-center justify-between mb-5">
        <span
          className="cp-pill"
          style={{ background: "rgba(71,129,255,0.20)", color: "var(--tint-blue)" }}
        >
          DESTACADO
        </span>
        <MatchClock startingAt={f.starting_at} status={f.state} />
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0 text-center">
          <TeamCrest
            name={f.home_team_name}
            shortCode={f.home_team_short}
            logoUrl={f.home_team_logo}
            primaryColor={f.home_team_primary_color}
            secondaryColor={f.home_team_secondary_color}
            size="lg"
            className="mx-auto mb-2"
          />
          <p
            style={{
              fontWeight: 600,
              fontSize: "0.875rem",
              color: "var(--label-primary)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {f.home_team_name}
          </p>
        </div>

        <div className="text-center shrink-0 px-4">
          {isFinished ? (
            <p
              className="ios-num"
              style={{
                fontSize: "2rem",
                fontWeight: 800,
                color: "var(--label-primary)",
              }}
            >
              {f.home_score}–{f.away_score}
            </p>
          ) : (
            <p
              className="cp-text-gradient"
              style={{ fontSize: "1.5rem", fontWeight: 800 }}
            >
              vs
            </p>
          )}
        </div>

        <div className="flex-1 min-w-0 text-center">
          <TeamCrest
            name={f.away_team_name}
            shortCode={f.away_team_short}
            logoUrl={f.away_team_logo}
            primaryColor={f.away_team_primary_color}
            secondaryColor={f.away_team_secondary_color}
            size="lg"
            className="mx-auto mb-2"
          />
          <p
            style={{
              fontWeight: 600,
              fontSize: "0.875rem",
              color: "var(--label-primary)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {f.away_team_name}
          </p>
        </div>
      </div>

      {p?.predicted_outcome && (
        <div
          className="mt-5 pt-4"
          style={{ borderTop: "1px solid var(--separator)", display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <span
            style={{
              padding: "5px 10px",
              borderRadius: 6,
              background: "var(--tint-blue-bg)",
              color: "var(--tint-blue)",
              fontSize: "0.75rem",
              fontWeight: 700,
            }}
          >
            {pickLabel}
          </span>
          {p.confidence !== null && (
            <span
              className="cp-text-gradient"
              style={{ fontSize: "1.5rem", fontWeight: 800 }}
            >
              {(p.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}
    </Link>
  );
}

// ─── Quick link (2x2 grid) ──────────────────────────────────────────────
function QuickLink({
  href,
  label,
  sub,
}: {
  href: string;
  label: string;
  sub: string;
}) {
  return (
    <Link href={href} className="cp-cta-secondary block" style={{ padding: "14px 16px" }}>
      <div style={{ fontWeight: 700, color: "var(--label-primary)", fontSize: "0.875rem" }}>
        {label}
      </div>
      <div
        style={{
          fontSize: "0.7rem",
          color: "var(--tint-blue)",
          marginTop: 4,
          fontWeight: 600,
        }}
      >
        {sub}
      </div>
    </Link>
  );
}

// ─── Empty state ────────────────────────────────────────────────────────
function EmptyState({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div
      className="ios-card text-center"
      style={{ padding: "32px 20px" }}
    >
      <h3
        style={{
          fontSize: "1rem",
          fontWeight: 700,
          color: "var(--label-primary)",
        }}
      >
        {title}
      </h3>
      <p
        style={{
          fontSize: "0.875rem",
          color: "var(--label-tertiary)",
          marginTop: 6,
        }}
      >
        {subtitle}
      </p>
    </div>
  );
}

// ─── Streak calculation (replaced by stats.current_streak) ───────────────
// Función eliminada — usamos stats.current_streak.length directamente.