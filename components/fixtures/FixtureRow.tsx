"use client";
// FixtureRow — compact row for match lists (iOS Settings-style)
// Usage: inside ListGroup or standalone
import Link from "next/link";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { PickBadge } from "./PickBadge";
import { MatchClock } from "./MatchClock";

interface FixtureRowProps {
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
  fixture: f,
  prediction,
  matchdayOrdinal,
  showVenue = false,
  showPick = true,
}: FixtureRowProps) {
  const isFinished = f.home_score !== null && f.away_score !== null;
  const homeScore = f.home_score ?? 0;
  const awayScore = f.away_score ?? 0;
  const realOutcome = isFinished
    ? homeScore > awayScore
      ? "home_win"
      : homeScore < awayScore
      ? "away_win"
      : "draw"
    : null;

  return (
    <Link
      href={`/partido/${f.id}`}
      className="ios-list-row ios-list-row-hover"
    >
      {/* Home crest + name */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <TeamCrest
          name={f.home_team_name}
          shortCode={f.home_team_short}
          logoUrl={f.home_team_logo}
          primaryColor={f.home_team_primary_color}
          secondaryColor={f.home_team_secondary_color}
          size="sm"
        />
        <span
          className="ios-body font-medium truncate flex-1"
          style={{ color: "var(--label-primary)" }}
        >
          {f.home_team_name}
        </span>

        {/* Score or pick */}
        <div className="shrink-0 flex flex-col items-center gap-1">
          {isFinished ? (
            <span
              className="ios-subhead font-bold ios-num"
              style={{ color: "var(--label-primary)" }}
            >
              {homeScore}–{awayScore}
            </span>
          ) : (
            prediction?.predicted_outcome && (
              <PickBadge outcome={prediction.predicted_outcome} size="sm" />
            )
          )}
        </div>

        {/* Away name + crest */}
        <span
          className="ios-body font-medium truncate flex-1 text-right"
          style={{ color: "var(--label-primary)" }}
        >
          {f.away_team_name}
        </span>
        <TeamCrest
          name={f.away_team_name}
          shortCode={f.away_team_short}
          logoUrl={f.away_team_logo}
          primaryColor={f.away_team_primary_color}
          secondaryColor={f.away_team_secondary_color}
          size="sm"
        />
      </div>

      {/* Right: time + matchday + chevron */}
      <div className="shrink-0 ml-3 flex items-center gap-2">
        <div className="flex flex-col items-end gap-0.5">
          <MatchClock startingAt={f.starting_at} status={f.state} compact />
          {matchdayOrdinal !== null && matchdayOrdinal !== undefined && (
            <span
              className="ios-caption"
              style={{ color: "var(--label-tertiary)" }}
            >
              J{matchdayOrdinal}
            </span>
          )}
        </div>
        <svg
          width="6"
          height="10"
          viewBox="0 0 6 10"
          fill="none"
          className="opacity-30 shrink-0"
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
      </div>
    </Link>
  );
}
