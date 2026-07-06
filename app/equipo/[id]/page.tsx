/**
 * /equipo/[id] — Perfil de equipo con stats y últimos partidos.
 */
import { notFound } from "next/navigation";
import Link from "next/link";
import { getTeamById, getTeamRecentFixtures, getTeamUpcomingFixtures } from "@/lib/db";
import { validateTeamId } from "@/lib/validation";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { Badge } from "@/components/ui/ios";
import { ListGroup, ListRow } from "@/components/ui/ListGroup";
import { MatchClock } from "@/components/fixtures/MatchClock";
import { BackButton } from "@/components/layout";

export const dynamic = "force-dynamic";

interface Props {
  params: { id: string };
}

export default function EquipoPage({ params }: Props) {
  const teamId = validateTeamId(params.id);
  if (teamId === null) notFound();

  const team = getTeamById(teamId);
  if (!team) notFound();

  const recent = getTeamRecentFixtures(teamId, 10);
  const upcoming = getTeamUpcomingFixtures(teamId, 5);

  // W/D/L stats
  const finished = recent.filter((f) => f.home_score !== null);
  const wins = finished.filter((f) => {
    const hs = f.home_score ?? 0;
    const as = f.away_score ?? 0;
    const isHome = f.home_team_id === teamId;
    return (isHome && hs > as) || (!isHome && as > hs);
  }).length;
  const draws = finished.filter((f) => (f.home_score ?? 0) === (f.away_score ?? 0)).length;
  const losses = finished.length - wins - draws;

  return (
    <div className="space-y-6 animate-ios-up">
      {/* ─── Header ─── */}
      <div className="ios-card" style={{ padding: "20px" }}>
        {team.primary_color && (
          <div
            className="absolute top-0 left-0 right-0 h-1 rounded-t-[14px]"
            style={{ background: team.primary_color }}
          />
        )}
        <div className="mb-3">
          <BackButton href="/equipos" label="Equipos" />
        </div>
        <div className="flex items-center gap-4 mt-2">
          <TeamCrest
            name={team.name}
            shortCode={team.short_code}
            logoUrl={team.logo_url}
            primaryColor={team.primary_color}
            secondaryColor={team.secondary_color}
            size="lg"
          />
          <div>
            <h1 className="ios-title-2 font-bold" style={{ color: "var(--label-primary)" }}>
              {team.name}
            </h1>
            <p className="ios-subhead mt-0.5" style={{ color: "var(--label-secondary)" }}>
              {[team.short_code, team.country, team.founded ? `Fundado ${team.founded}` : null]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
        </div>
      </div>

      {/* ─── W/D/L compact ─── */}
      {finished.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Victorias", value: wins, color: "#30D158" },
            { label: "Empates", value: draws, color: "rgba(235,235,245,0.5)" },
            { label: "Derrotas", value: losses, color: "#FF453A" },
          ].map(({ label, value, color }) => (
            <div
              key={label}
              className="ios-card text-center py-4"
              style={{ background: "var(--bg-elevated)" }}
            >
              <p className="ios-title-2 font-bold ios-num" style={{ color }}>
                {value}
              </p>
              <p className="ios-caption mt-1" style={{ color: "var(--label-secondary)" }}>
                {label}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* ─── Próximos partidos ─── */}
      {upcoming.length > 0 && (
        <ListGroup header="Próximos partidos">
          {upcoming.map((f) => {
            const isHome = f.home_team_id === teamId;
            return (
              <Link key={f.id} href={`/partido/${f.id}`} className="ios-list-row ios-list-row-hover">
                <div className="flex-1 min-w-0">
                  <p className="ios-body" style={{ color: "var(--label-primary)" }}>
                    {isHome ? f.away_team_name : `@ ${f.away_team_name}`}
                  </p>
                  <p className="ios-caption mt-0.5" style={{ color: "var(--label-secondary)" }}>
                    {isHome ? "Local" : "Visita"}
                  </p>
                </div>
                <div className="shrink-0 ml-3">
                  <MatchClock startingAt={f.starting_at} status={f.state} compact />
                </div>
              </Link>
            );
          })}
        </ListGroup>
      )}

      {/* ─── Últimos partidos ─── */}
      <ListGroup header={`Últimos ${finished.length} partidos`}>
        {recent.map((f) => {
          const isHome = f.home_team_id === teamId;
          const hs = f.home_score ?? 0;
          const as = f.away_score ?? 0;
          const teamScore = isHome ? hs : as;
          const oppScore = isHome ? as : hs;
          const won = teamScore > oppScore;
          const drew = teamScore === oppScore;

          const outcomeColor = won ? "#30D158" : drew ? "rgba(235,235,245,0.5)" : "#FF453A";

          return (
            <Link key={f.id} href={`/partido/${f.id}`} className="ios-list-row ios-list-row-hover">
              <div className="flex-1 min-w-0">
                <p className="ios-body" style={{ color: "var(--label-primary)" }}>
                  {isHome ? "vs" : "@"} {isHome ? f.away_team_name : f.home_team_name}
                </p>
                <p className="ios-caption mt-0.5" style={{ color: "var(--label-tertiary)" }}>
                  {new Date(f.starting_at).toLocaleDateString("es-MX", {
                    day: "numeric",
                    month: "short",
                  })}
                </p>
              </div>
              <div className="shrink-0 ml-3 flex items-center gap-2">
                <span className="ios-headline font-bold ios-num" style={{ color: "var(--label-primary)" }}>
                  {teamScore}–{oppScore}
                </span>
                <Badge color={won ? "green" : drew ? "neutral" : "red"} size="sm">
                  {won ? "W" : drew ? "D" : "L"}
                </Badge>
              </div>
            </Link>
          );
        })}
      </ListGroup>
    </div>
  );
}
