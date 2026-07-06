/**
 * PredictionCard — Migrado del front viejo (Quiniela Express).
 *
 * Patrones rescatados:
 * - Tres barras de probabilidad con colores semánticos (emerald/slate/blue)
 * - Score visible en chip azul si terminado
 * - Badge "🤖 IA" cuando hay predicción
 * - Estado del partido (FT/PROX) en pill
 * - Hover effect (border blue + shadow + lift)
 * - Loading state con animación pulse
 * - Indicador de predicción acertada/fallida
 *
 * Adaptación al sistema nuevo:
 * - Mantenemos read-only (sin save button, sin simulación clickeable)
 * - Toda la card es un link a /partido/[id]
 */

import Link from "next/link";
import ProbabilityBars from "./ProbabilityBars";
import ResultIndicator from "./ResultIndicator";
import { getMatchdayOrdinalByDate } from "@/lib/db";

interface Prediction {
  home_win_prob: number | null;
  draw_prob: number | null;
  away_win_prob: number | null;
  predicted_outcome: string | null;
}

interface Fixture {
  id: number;
  starting_at: string;
  home_team_name: string;
  away_team_name: string;
  home_team_short: string | null;
  away_team_short: string | null;
  home_score: number | null;
  away_score: number | null;
  matchday?: number | null;
  season_id?: number | null;
}

export default function PredictionCard({
  fixture,
  prediction,
}: {
  fixture: Fixture;
  prediction?: Prediction | null;
}) {
  const isFinished = fixture.home_score !== null && fixture.away_score !== null;
  // SIEMPRE mostrar nombre completo del equipo (no abreviado).
  // El short_code (3 letras) no es identificable para usuarios no expertos.
  const homeShort = fixture.home_team_name;
  const awayShort = fixture.away_team_name;
  const matchdayOrd = getMatchdayOrdinalByDate(
    fixture.season_id ?? null,
    fixture.matchday ?? null,
    fixture.starting_at ?? null
  );

  return (
    <Link
      href={`/partido/${fixture.id}`}
      className="card card-hover relative block group p-4 sm:p-5"
    >
      {/* Header: estado + fecha */}
      <div
        className={`flex justify-between items-center mb-4 ${
          prediction?.predicted_outcome ? "pl-10 sm:pl-14" : ""
        }`}
      >
        <span className={isFinished ? "badge-finished" : "badge-scheduled"}>
          {isFinished ? "FT" : "PRÓX"}
        </span>
        <span className="label-xs">
          {new Date(fixture.starting_at).toLocaleDateString("es-MX", {
            weekday: "short",
            day: "numeric",
            month: "short",
          })}
        </span>
      </div>

      {/* Equipos + score */}
      <div className="flex justify-between items-center gap-3 mb-5">
        <div className="text-center flex-1 min-w-0">
          <p className="font-bold text-white leading-tight truncate">
            {homeShort}
          </p>
        </div>
        <div className="px-3 py-1 bg-slate-800 rounded-lg shrink-0">
          <span className="text-lg font-black text-blue-400 tracking-tight">
            {isFinished
              ? `${fixture.home_score} - ${fixture.away_score}`
              : "vs"}
          </span>
        </div>
        <div className="text-center flex-1 min-w-0">
          <p className="font-bold text-white leading-tight truncate">
            {awayShort}
          </p>
        </div>
      </div>

      {/* Probabilidades (solo si hay predicción) */}
      {prediction?.predicted_outcome && (
        <div className="border-t border-slate-800 pt-4">
          <ProbabilityBars
            homePct={prediction.home_win_prob ?? 0.33}
            drawPct={prediction.draw_prob ?? 0.33}
            awayPct={prediction.away_win_prob ?? 0.33}
          />
          {prediction.predicted_outcome && (
            <p className="label-mini mt-3 text-center">
              Pick:{" "}
              <span className="text-blue-400 font-black">
                {prediction.predicted_outcome === "home_win"
                  ? "Local"
                  : prediction.predicted_outcome === "away_win"
                  ? "Visita"
                  : "Empate"}
              </span>
              {matchdayOrd !== null && (
                <span className="text-slate-600"> · J{matchdayOrd}</span>
              )}
            </p>
          )}
        </div>
      )}

      {/* Indicador resultado */}
      {isFinished && (
        <ResultIndicator
          predictedOutcome={prediction?.predicted_outcome}
          homeScore={fixture.home_score}
          awayScore={fixture.away_score}
        />
      )}

      {/* Hover CTA */}
      <div className="mt-4 pt-3 border-t border-slate-800/50 flex justify-between items-center text-[10px] font-black uppercase tracking-widest text-slate-600 group-hover:text-blue-400 transition-colors">
        <span>{isFinished ? "Ver partido" : "Ver análisis"}</span>
        <span className="group-hover:translate-x-1 transition-transform">
          →
        </span>
      </div>
    </Link>
  );
}