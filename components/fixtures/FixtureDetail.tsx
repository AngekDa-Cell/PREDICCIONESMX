"use client";
// FixtureDetail — compact row for list views (iOS Settings-style)
// Usage: inside ListGroup or standalone
import Link from "next/link";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { PickBadge } from "./PickBadge";
import { MatchClock } from "./MatchClock";

interface FixtureDetailProps {
  fixture: {
    id: number;
    starting_at: string;
    home_team_id: number;
    away_team_id: number;
    home_team_name: string;
    away_team_name: string;
    home_team_short?: string | null;
    away_team_short?: string | null;
    home_team_logo?: string | null;
    away_team_logo?: string | null;
    home_team_primary_color?: string | null;
    home_team_secondary_color?: string | null;
    away_team_primary_color?: string | null;
    away_team_secondary_color?: string | null;
    home_score: number | null;
    away_score: number | null;
    state?: string | null;
    venue_name?: string | null;
  };
  prediction?: {
    predicted_outcome: string | null;
    confidence: number | null;
    most_likely_score?: string | null;
  } | null;
  matchdayOrdinal?: number | null;
  showVenue?: boolean;
  showPick?: boolean;
}

export function FixtureRow({
  fixture,
  prediction,
  matchdayOrdinal,
  showVenue = false,
  showPick = true,
}: FixtureDetailProps) {
  const isFinished =
    fixture.home_score !== null && fixture.away_score !== null;
  const homeScore = fixture.home_score ?? 0;
  const awayScore = fixture.away_score ?? 0;

  const realOutcome = isFinished
    ? homeScore > awayScore
      ? "home_win"
      : homeScore < awayScore
      ? "away_win"
      : "draw"
    : null;

  return (
    <Link
      href={`/partido/${fixture.id}`}
      className="ios-list-row ios-list-row-hover"
    >
      {/* Left: team info + match info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {/* Home team */}
          <TeamCrest
            name={fixture.home_team_name}
            shortCode={fixture.home_team_short}
            logoUrl={fixture.home_team_logo}
            primaryColor={fixture.home_team_primary_color}
            secondaryColor={fixture.home_team_secondary_color}
            size="sm"
          />
          <span className="ios-body font-medium truncate flex-1 min-w-0">
            {fixture.home_team_name}
          </span>
          {/* Score */}
          <span
            className={`ios-headline font-bold tabular-nums shrink-0 ${
              isFinished ? "" : "opacity-0"
            }`}
            style={{ color: isFinished ? "var(--label-primary)" : undefined }}
          >
            {isFinished ? `${fixture.home_score}–${fixture.away_score}` : "–:–"}
          </span>
          {/* Away team */}
          <span className="ios-body font-medium truncate flex-1 min-w-0 text-right">
            {fixture.away_team_name}
          </span>
          <TeamCrest
            name={fixture.away_team_name}
            shortCode={fixture.away_team_short}
            logoUrl={fixture.away_team_logo}
            primaryColor={fixture.away_team_primary_color}
            secondaryColor={fixture.away_team_secondary_color}
            size="sm"
          />
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <MatchClock startingAt={fixture.starting_at} status={fixture.state} compact />
          {matchdayOrdinal !== null && matchdayOrdinal !== undefined && (
            <span
              className="ios-caption"
              style={{ color: "var(--label-tertiary)" }}
            >
              J{matchdayOrdinal}
            </span>
          )}
          {showVenue && fixture.venue_name && (
            <span
              className="ios-caption truncate max-w-[120px]"
              style={{ color: "var(--label-tertiary)" }}
            >
              📍 {fixture.venue_name}
            </span>
          )}
          {/* Show result indicator */}
          {isFinished && prediction?.predicted_outcome && (
            <span
              className={`ios-caption font-semibold ${
                realOutcome === prediction.predicted_outcome
                  ? "text-[#30D158]"
                  : "text-[#FF453A]"
              }`}
            >
              {realOutcome === prediction.predicted_outcome ? "✓" : "✘"}
            </span>
          )}
        </div>
      </div>

      {/* Right: pick */}
      {showPick && !isFinished && prediction?.predicted_outcome && (
        <PickBadge
          outcome={prediction.predicted_outcome}
          confidence={prediction.confidence}
          size="sm"
        />
      )}

      {/* Chevron */}
      <svg
        width="6"
        height="10"
        viewBox="0 0 6 10"
        fill="none"
        className="shrink-0 ml-2 opacity-30"
        aria-hidden="true"
      >
        <path
          d="M1 1L5 5L1 9"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </Link>
  );
}
