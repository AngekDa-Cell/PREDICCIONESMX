/**
 * StatsBadge — Panel de efectividad del modelo numérico.
 * Migrado del patrón del front viejo + custom para historial.
 *
 * Muestra: accuracy, brier, breakdown por outcome, racha actual.
 */

import type { HistoryStats } from "@/lib/db";

export default function StatsBadge({ stats }: { stats: HistoryStats }) {
  const accPct = stats.accuracy !== null ? (stats.accuracy * 100).toFixed(1) : "—";
  const brier = stats.brier !== null ? stats.brier.toFixed(4) : "—";
  const accColor =
    stats.accuracy === null
      ? "text-slate-400"
      : stats.accuracy >= 0.55
      ? "text-emerald-400"
      : stats.accuracy >= 0.45
      ? "text-yellow-400"
      : "text-red-400";

  return (
    <div className="card border-blue-500/30 bg-blue-500/5">
      <span className="label-mini">Efectividad del Modelo</span>

      {/* Accuracy destacada */}
      <div className="flex items-baseline gap-3 mt-2 mb-4">
        <div className={`text-5xl font-black ${accColor}`}>{accPct}%</div>
        <div className="text-xs text-slate-400 leading-tight">
          <div>
            <strong className="text-white">{stats.hits}</strong>/{stats.finished} aciertos
          </div>
          <div className="mt-1">evaluados</div>
        </div>
      </div>

      {/* Mensaje honesto si no hay predicciones live evaluadas */}
      {stats.finished === 0 && (
        <div className="mb-4 px-3 py-2 rounded-md bg-slate-900/60 border border-slate-800 text-[11px] text-slate-400 leading-relaxed">
          Aún no hay predicciones <strong className="text-slate-300">live</strong> evaluadas.
          El modelo empieza a contar cuando los partidos se juegan.
          Los <strong className="text-slate-300">backtest</strong> abajo son predicciones
          retrospectivas y no cuentan para la efectividad.
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-blue-500/20">
        <StatMini
          label="Brier"
          value={brier}
          tooltip="Brier score promedio (menor = mejor). Random ~0.667, baseline home_advantage ~0.611"
          hint="↓ mejor"
        />
        <StatMini
          label="Total"
          value={stats.total.toString()}
          tooltip="Total de predicciones generadas"
        />
        <StatMini
          label="Pendientes"
          value={stats.pending.toString()}
          tooltip="Partidos futuros aún no jugados"
        />
        <StatMini
          label="Racha"
          value={
            stats.current_streak.type
              ? `${stats.current_streak.length}${
                  stats.current_streak.type === "W" ? "W" : "L"
                }`
              : "—"
          }
          tooltip="Racha actual de aciertos (W) o fallos (L) consecutivos"
        />
      </div>

      {/* Breakdown por outcome */}
      <div className="pt-3 mt-3 border-t border-blue-500/20">
        <span className="label-mini">Por tipo de pick</span>
        <div className="grid grid-cols-3 gap-2 mt-2">
          <OutcomeRow
            label="Local"
            data={stats.by_outcome.home_win}
            color="emerald"
          />
          <OutcomeRow label="Empate" data={stats.by_outcome.draw} color="slate" />
          <OutcomeRow
            label="Visita"
            data={stats.by_outcome.away_win}
            color="blue"
          />
        </div>
      </div>

      {/* Last 5 */}
      {stats.last_5.length > 0 && (
        <div className="pt-3 mt-3 border-t border-blue-500/20 flex items-center justify-between">
          <span className="label-mini">Últimos 5</span>
          <div className="flex gap-1.5">
            {stats.last_5.map((r, i) => (
              <span
                key={i}
                className={`w-7 h-7 rounded-md flex items-center justify-center font-black text-xs ${
                  r === "W"
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : r === "L"
                    ? "bg-red-500/20 text-red-400 border border-red-500/30"
                    : "bg-slate-800 text-slate-500 border border-slate-700"
                }`}
              >
                {r === "W" ? "✓" : r === "L" ? "✘" : "—"}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatMini({
  label,
  value,
  tooltip,
  hint,
}: {
  label: string;
  value: string;
  tooltip?: string;
  hint?: string;
}) {
  return (
    <div title={tooltip}>
      <div className="text-lg font-black text-white">{value}</div>
      <div className="label-mini mt-0.5">
        {label}
        {hint && <span className="text-slate-600"> {hint}</span>}
      </div>
    </div>
  );
}

function OutcomeRow({
  label,
  data,
  color,
}: {
  label: string;
  data: { total: number; hits: number; accuracy: number | null };
  color: "emerald" | "slate" | "blue";
}) {
  const pct =
    data.accuracy !== null ? `${(data.accuracy * 100).toFixed(0)}%` : "—";
  const textColor =
    color === "emerald"
      ? "text-emerald-400"
      : color === "blue"
      ? "text-blue-400"
      : "text-slate-400";
  return (
    <div className="text-center">
      <div className={`text-xl font-black ${textColor}`}>{pct}</div>
      <div className="label-mini mt-0.5">
        {label} ({data.hits}/{data.total})
      </div>
    </div>
  );
}