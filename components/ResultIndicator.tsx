/**
 * ResultIndicator — Migrado del PredictionCard viejo.
 *
 * Muestra si la predicción fue correcta o no después de un partido terminado.
 * Verde para acertada, rojo para fallida. Patrón uppercase tracking-widest.
 */
export default function ResultIndicator({
  predictedOutcome,
  homeScore,
  awayScore,
}: {
  predictedOutcome: string | null | undefined;
  homeScore: number | null;
  awayScore: number | null;
}) {
  if (
    homeScore === null ||
    awayScore === null ||
    !predictedOutcome
  ) {
    return null;
  }

  const real =
    homeScore > awayScore
      ? "home_win"
      : homeScore < awayScore
      ? "away_win"
      : "draw";

  const correct = predictedOutcome === real;

  return (
    <div
      className={`mt-3 py-1.5 px-3 rounded-xl text-[10px] font-black text-center tracking-widest border ${
        correct ? "result-correct" : "result-incorrect"
      }`}
      title="Backtest honesto: predicción del ensemble numérico (xG + Elo + DC) generada con datos hasta la fecha del partido"
    >
      {correct ? "✓ BACKTEST · ACIERTO" : "✘ BACKTEST · FALLO"}
    </div>
  );
}