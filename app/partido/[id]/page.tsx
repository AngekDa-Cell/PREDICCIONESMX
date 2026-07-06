/**
 * /partido/[id] — Análisis completo de un partido.
 * Propósito único: toda la información para decidir tu quiniela.
 * - Pick + confianza
 * - Probabilidades 1X2
 * - Razones del modelo
 * - Riesgo (contrarian view)
 * - Resultado real si terminó
 */
import { notFound } from "next/navigation";
import Link from "next/link";
import {
  getFixtureById,
  getPredictionView,
  getMatchdayOrdinalByDate,
} from "@/lib/db";
import { validateFixtureId } from "@/lib/validation";
import { ListGroup, ListRow } from "@/components/ui/ListGroup";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { ProbabilityBars } from "@/components/ui/ProbabilityBars";
import { Badge } from "@/components/ui/ios";
import { BackButton } from "@/components/layout";
import { CrowdSummary } from "@/components/votes/CrowdSummary";
import { makeToken } from "@/lib/votes/token";
import { getCrowdSummary } from "@/lib/db/votes";

export const dynamic = "force-dynamic";

interface Props {
  params: { id: string };
}

const PICK_LABEL: Record<string, string> = {
  home_win: "Local",
  away_win: "Visita",
  draw: "Empate",
};

export default function PartidoPage({ params }: Props) {
  const fixtureId = validateFixtureId(params.id);
  if (fixtureId === null) notFound();

  const fixture = getFixtureById(fixtureId);
  if (!fixture) notFound();

  const prediction = getPredictionView(fixtureId);
  const isFinished = fixture.home_score !== null && fixture.away_score !== null;
  const homeScore = fixture.home_score ?? 0;
  const awayScore = fixture.away_score ?? 0;
  const startMs = new Date(fixture.starting_at).getTime();

  const matchdayOrd = getMatchdayOrdinalByDate(
    fixture.season_id,
    fixture.matchday,
    fixture.starting_at,
  );

  const pickLabel = prediction?.predicted_outcome
    ? PICK_LABEL[prediction.predicted_outcome] ?? prediction.predicted_outcome
    : null;

  const realOutcome = isFinished
    ? homeScore > awayScore
      ? "home_win"
      : homeScore < awayScore
      ? "away_win"
      : "draw"
    : null;

  const pickCorrect =
    prediction?.predicted_outcome !== null &&
    prediction?.predicted_outcome !== undefined &&
    realOutcome !== null
      ? prediction.predicted_outcome === realOutcome
      : null;

  // Voto crowd + token compartible
  const voteToken = makeToken(fixtureId);
  const crowdSummary = getCrowdSummary(fixtureId);
  const votingEnabled = !isFinished && startMs > Date.now();
  return (
    <div className="space-y-6 animate-ios-up">
      {/* ─── Match header ─── */}
      <div className="ios-card" style={{ padding: "20px" }}>
        <div className="mb-3">
          <BackButton href="/" label="Inicio" />
        </div>

        {/* Meta */}
        <p className="ios-footnote mb-4" style={{ color: "var(--label-secondary)" }}>
          {new Date(fixture.starting_at).toLocaleDateString("es-MX", {
            weekday: "long",
            day: "2-digit",
            month: "long",
            year: "numeric",
          })}
          {" · "}
          {new Date(fixture.starting_at).toLocaleTimeString("es-MX", {
            hour: "2-digit",
            minute: "2-digit",
          })}
          {matchdayOrd !== null && ` · Jornada ${matchdayOrd}`}
          {fixture.season_name && ` · ${fixture.season_name}`}
        </p>

        {/* Teams + score */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex-1 min-w-0 text-center">
            <TeamCrest
              name={fixture.home_team_name}
              shortCode={fixture.home_team_short}
              logoUrl={fixture.home_team_logo}
              primaryColor={fixture.home_team_primary_color}
              secondaryColor={fixture.home_team_secondary_color}
              size="lg"
              className="mx-auto mb-2"
            />
            <p className="ios-headline font-semibold truncate" style={{ color: "var(--label-primary)" }}>
              {fixture.home_team_name}
            </p>
          </div>

          <div className="text-center shrink-0 px-4">
            {isFinished ? (
              <p className="ios-title-1 font-bold ios-num" style={{ color: "var(--label-primary)" }}>
                {homeScore}–{awayScore}
              </p>
            ) : (
              <p className="ios-title-2 font-bold" style={{ color: "var(--tint-blue)" }}>
                vs
              </p>
            )}
          </div>

          <div className="flex-1 min-w-0 text-center">
            <TeamCrest
              name={fixture.away_team_name}
              shortCode={fixture.away_team_short}
              logoUrl={fixture.away_team_logo}
              primaryColor={fixture.away_team_primary_color}
              secondaryColor={fixture.away_team_secondary_color}
              size="lg"
              className="mx-auto mb-2"
            />
            <p className="ios-headline font-semibold truncate" style={{ color: "var(--label-primary)" }}>
              {fixture.away_team_name}
            </p>
          </div>
        </div>

        {/* Derby badge */}
        {prediction?.derby_flag === 1 && prediction?.derby_name && (
          <div className="mt-4 text-center">
            <Badge color="orange">
              🔥 {prediction.derby_name}
            </Badge>
          </div>
        )}

        {/* Venue */}
        {fixture.venue_name && (
          <p className="ios-caption text-center mt-3" style={{ color: "var(--label-tertiary)" }}>
            📍 {fixture.venue_name}
            {fixture.venue_capacity && ` · ${fixture.venue_capacity.toLocaleString()} capacidade`}
          </p>
        )}
      </div>

      {/* ─── Prediction ─── */}
      {prediction && prediction.predicted_outcome !== null ? (
        <>
          {/* Pick + confidence */}
          <div
            className="ios-card"
            style={{
              padding: "20px",
              background: "var(--tint-blue-bg)",
              border: "0.5px solid rgba(10,132,255,0.3)",
            }}
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="ios-caption mb-1" style={{ color: "var(--label-secondary)" }}>
                  Predicción del modelo
                </p>
                <p className="ios-title-1 font-bold" style={{ color: "var(--tint-blue)" }}>
                  {pickLabel}
                </p>
                {prediction.most_likely_score && (
                  <p className="ios-subhead mt-1" style={{ color: "var(--label-secondary)" }}>
                    Marcador esperado:{" "}
                    <strong style={{ color: "var(--label-primary)" }}>
                      {prediction.most_likely_score}
                    </strong>
                  </p>
                )}
              </div>
              {prediction.confidence !== null && (
                <div className="text-right">
                  <p className="ios-caption mb-1" style={{ color: "var(--label-secondary)" }}>
                    Confianza
                  </p>
                  <p className="ios-title-1 font-bold ios-num" style={{ color: "var(--label-primary)" }}>
                    {(prediction.confidence * 100).toFixed(0)}%
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Probabilities */}
          <div className="ios-card">
            <p className="ios-callout font-semibold mb-4" style={{ color: "var(--label-primary)" }}>
              Probabilidades
            </p>
            <ProbabilityBars
              home={prediction.home_win_prob ?? 0.33}
              draw={prediction.draw_prob ?? 0.33}
              away={prediction.away_win_prob ?? 0.33}
            />
          </div>

          {/* Key factors */}
          {prediction.key_factors && (
            <div className="ios-card">
              <p className="ios-callout font-semibold mb-2" style={{ color: "var(--label-primary)" }}>
                ¿Por qué este pick?
              </p>
              <p className="ios-body leading-relaxed" style={{ color: "var(--label-secondary)" }}>
                {prediction.key_factors}
              </p>
            </div>
          )}

          {/* Contrarian view */}
          {prediction.contrarian_view && (
            <div
              className="ios-card"
              style={{
                background: "rgba(255,159,10,0.08)",
                border: "0.5px solid rgba(255,159,10,0.25)",
              }}
            >
              <div className="flex items-center gap-2 mb-2">
                <span style={{ color: "#FF9F0A" }}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 2L14 13H2L8 2Z" stroke="#FF9F0A" strokeWidth="1.5" strokeLinejoin="round"/>
                    <path d="M8 6v4M8 11.5v.5" stroke="#FF9F0A" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                </span>
                <p className="ios-callout font-semibold" style={{ color: "#FF9F0A" }}>
                  Riesgo del pick
                </p>
              </div>
              <p className="ios-body leading-relaxed" style={{ color: "var(--label-secondary)" }}>
                {prediction.contrarian_view}
              </p>
            </div>
          )}
        </>
      ) : (
        <div className="ios-card text-center py-8">
          <p className="ios-headline" style={{ color: "var(--label-tertiary)" }}>
            Sin predicción todavía
          </p>
          <p className="ios-subhead mt-1" style={{ color: "var(--label-quaternary)" }}>
            El modelo aún no ha analizado este partido
          </p>
        </div>
      )}

      {/* ─── Crowd vote ─── */}
      <CrowdSummary
        fixtureId={fixtureId}
        token={voteToken}
        summary={crowdSummary}
        votingEnabled={votingEnabled}
      />

      {/* ─── Result (if finished) ─── */}
      {isFinished && (
        <div
          className="ios-card"
          style={{
            background:
              pickCorrect === true
                ? "rgba(48,209,88,0.08)"
                : "rgba(255,69,58,0.08)",
            border:
              pickCorrect === true
                ? "0.5px solid rgba(48,209,88,0.3)"
                : "0.5px solid rgba(255,69,58,0.3)",
          }}
        >
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="ios-caption mb-1" style={{ color: "var(--label-secondary)" }}>
                Resultado real
              </p>
              <p
                className="ios-title-2 font-bold"
                style={{
                  color:
                    realOutcome === "home_win"
                      ? "#30D158"
                      : realOutcome === "away_win"
                      ? "#0A84FF"
                      : "rgba(235,235,245,0.5)",
                }}
              >
                {PICK_LABEL[realOutcome ?? ""]}
                <span
                  className="ios-title-2 font-bold ios-num ml-3"
                  style={{ color: "var(--label-primary)" }}
                >
                  {homeScore}–{awayScore}
                </span>
              </p>
              {prediction && (
                <p className="ios-footnote mt-1" style={{ color: "var(--label-tertiary)" }}>
                  El modelo dijo{" "}
                  <strong style={{ color: "var(--label-secondary)" }}>
                    {pickLabel}
                  </strong>
                </p>
              )}
            </div>
            <div
              className="ios-title-1 font-black"
              style={{ color: pickCorrect === true ? "#30D158" : "#FF453A" }}
            >
              {pickCorrect === true ? "✓" : "✘"}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
