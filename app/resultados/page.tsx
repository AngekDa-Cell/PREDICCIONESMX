/**
 * /resultados — Track record del modelo.
 * Propósito: transparencia: qué tanto acierta, breakdown, racha.
 * SIN redundancia: no duplica /partidos ni /home.
 */
import Link from "next/link";
import { BackButton } from "@/components/layout";
import { getPredictionHistory, getHistoryStats } from "@/lib/db";
import { ListGroup, ListRow } from "@/components/ui/ListGroup";
import { StatsBadge } from "@/components/stats/StatsBadge";
import { Badge } from "@/components/ui/ios";
import { MatchClock } from "@/components/fixtures/MatchClock";

export const dynamic = "force-dynamic";

const MAX_ROWS = 40;
const PICK_LABEL: Record<string, string> = {
  home_win: "Local",
  away_win: "Visita",
  draw: "Empate",
};

export default function ResultadosPage() {
  const history = getPredictionHistory();
  const stats = getHistoryStats(history);

  // Solo terminados
  const finished = history
    .filter((h) => h.status === "finished")
    .sort(
      (a, b) =>
        new Date(b.starting_at).getTime() - new Date(a.starting_at).getTime(),
    )
    .slice(0, MAX_ROWS);

  return (
    <div className="space-y-6 animate-ios-up">
      <PageHeader
        title="Resultados"
        subtitle="Predicción vs resultado real"
      />

      {/* Stats panel */}
      <StatsBadge stats={stats} />

      {/* List */}
      {finished.length === 0 ? (
        <EmptyState />
      ) : (
        <ListGroup header={`Últimos ${finished.length} partidos evaluados`}>
          {finished.map((row) => (
            <ResultRow key={row.id} row={row} />
          ))}
        </ListGroup>
      )}

      {finished.length === 0 && stats.total > 0 && (
        <p className="ios-caption text-center pt-4" style={{ color: "var(--label-tertiary)" }}>
          Mostrando {finished.length} partidos evaluados · BT = Backtest (no cuenta para accuracy)
        </p>
      )}
    </div>
  );
}

function ResultRow({ row }: { row: ReturnType<typeof getPredictionHistory>[0] }) {
  const pickLabel = row.predicted_outcome
    ? PICK_LABEL[row.predicted_outcome]
    : null;
  const real =
    row.home_score !== null && row.away_score !== null
      ? row.home_score > row.away_score
        ? "home_win"
        : row.home_score < row.away_score
        ? "away_win"
        : "draw"
      : null;

  return (
    <Link href={`/partido/${row.fixture_id}`} className="ios-list-row ios-list-row-hover">
      {/* Left: teams + pick */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="ios-body font-medium truncate" style={{ color: "var(--label-primary)" }}>
            {row.home_team_name}
          </span>
          <span className="ios-caption shrink-0" style={{ color: "var(--label-tertiary)" }}>
            vs
          </span>
          <span className="ios-body font-medium truncate" style={{ color: "var(--label-primary)" }}>
            {row.away_team_name}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          {pickLabel && (
            <Badge
              color={
                row.predicted_outcome === "home_win"
                  ? "green"
                  : row.predicted_outcome === "away_win"
                  ? "blue"
                  : "neutral"
              }
              size="sm"
            >
              {pickLabel}
            </Badge>
          )}
          {row.most_likely_score && (
            <span className="ios-caption" style={{ color: "var(--label-tertiary)" }}>
              {row.most_likely_score}
            </span>
          )}
          {row.is_backtest && (
            <Badge color="yellow" size="sm">BT</Badge>
          )}
        </div>
      </div>

      {/* Right: score + result */}
      <div className="shrink-0 ml-3 flex items-center gap-2">
        <span className="ios-subhead font-bold ios-num" style={{ color: "var(--label-primary)" }}>
          {row.home_score}–{row.away_score}
        </span>
        {/* Outcome badge */}
        <Badge
          color={
            row.pick_correct === true
              ? "green"
              : row.pick_correct === false
              ? "red"
              : "neutral"
          }
          size="sm"
        >
          {row.pick_correct === true ? "✓" : row.pick_correct === false ? "✘" : "—"}
        </Badge>
        {/* Date */}
        <div className="hidden sm:block">
          <MatchClock startingAt={row.starting_at} status="FINISHED" compact />
        </div>
      </div>
    </Link>
  );
}

function PageHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="pb-3 mb-4">
      <BackButton href="/" label="Inicio" />
      <h1 className="ios-title-2 font-bold" style={{ color: "var(--label-primary)" }}>
        {title}
      </h1>
      <p className="ios-subhead mt-0.5" style={{ color: "var(--label-secondary)" }}>
        {subtitle}
      </p>
    </header>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-16 rounded-[14px]" style={{ background: "var(--bg-elevated)", border: "0.5px solid var(--hairline)" }}>
      <p className="ios-headline" style={{ color: "var(--label-secondary)" }}>
        Aún no hay partidos evaluados
      </p>
      <p className="ios-subhead mt-1" style={{ color: "var(--label-tertiary)" }}>
        Cuando se jueguen los partidos, se mostrarán aquí
      </p>
    </div>
  );
}
