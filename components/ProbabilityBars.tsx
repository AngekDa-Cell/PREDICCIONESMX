/**
 * ProbabilityBars — Migrado del PredictionCard viejo.
 *
 * Tres barras semánticas (Local/Empate/Visita) con colores:
 * - Local: emerald-500 (verde, victoria local)
 * - Empate: slate-500 (gris neutro)
 * - Visita: blue-500 (azul, victoria visitante)
 *
 * Patrón signature del front viejo: ProgressBar h-1.5 con transition-all duration-1000.
 */
export default function ProbabilityBars({
  homePct,
  drawPct,
  awayPct,
  size = "md",
}: {
  homePct: number;
  drawPct: number;
  awayPct: number;
  size?: "sm" | "md";
}) {
  const h = size === "sm" ? "h-1" : "h-1.5";
  const labelSize = size === "sm" ? "text-[9px]" : "text-[10px]";

  return (
    <div className="space-y-2.5">
      <Bar
        label="Local"
        value={homePct}
        color="bg-emerald-500"
        height={h}
        labelSize={labelSize}
      />
      <Bar
        label="Empate"
        value={drawPct}
        color="bg-slate-500"
        height={h}
        labelSize={labelSize}
      />
      <Bar
        label="Visita"
        value={awayPct}
        color="bg-blue-500"
        height={h}
        labelSize={labelSize}
      />
    </div>
  );
}

function Bar({
  label,
  value,
  color,
  height,
  labelSize,
}: {
  label: string;
  value: number;
  color: string;
  height: string;
  labelSize: string;
}) {
  const pct = Math.max(0, Math.min(1, value ?? 0));
  const width = (pct * 100).toFixed(1);
  return (
    <div>
      <div
        className={`flex justify-between mb-1 ${labelSize} uppercase tracking-widest text-slate-400 font-bold`}
      >
        <span>Prob. {label}</span>
        <span className="text-slate-200">{width}%</span>
      </div>
      <div className={`${height} w-full bg-slate-800 rounded-full overflow-hidden`}>
        <div
          className={`h-full ${color} transition-all duration-1000 ease-out`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}