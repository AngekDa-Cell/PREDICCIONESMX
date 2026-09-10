"use client";
// StatsBadge — iOS-style effectiveness panel
// Shows: accuracy ring, Brier, streak, last 5, breakdown by outcome
import { ProbabilityRing } from "@/components/ui/ProbabilityRing";

interface StatsBadgeProps {
  stats: {
    accuracy: number | null;
    finished: number;
    hits: number;
    misses: number;
    brier: number | null;
    total: number;
    pending: number;
    current_streak: { type: "W" | "L" | null; length: number };
    last_5: ("W" | "L" | null)[];
    by_outcome: Record<
      string,
      { total: number; hits: number; accuracy: number | null }
    >;
  };
}

const OUTCOME_LABELS: Record<string, { label: string; color: string }> = {
  home_win: { label: "Local", color: "#30D158" },
  draw: { label: "Empate", color: "rgba(235,235,245,0.5)" },
  away_win: { label: "Visita", color: "#0A84FF" },
};

function OutcomeRow({
  label,
  data,
  color,
}: {
  label: string;
  data: { total: number; hits: number; accuracy: number | null };
  color: string;
}) {
  const pct = data.accuracy !== null ? `${(data.accuracy * 100).toFixed(0)}%` : "—";
  return (
    <div className="flex-1 text-center">
      <p
        className="ios-title-3 font-bold"
        style={{ color: data.total > 0 ? color : "var(--label-tertiary)" }}
      >
        {pct}
      </p>
      <p className="ios-caption mt-0.5" style={{ color: "var(--label-secondary)" }}>
        {label}
      </p>
      <p className="ios-caption" style={{ color: "var(--label-tertiary)" }}>
        {data.hits}/{data.total}
      </p>
    </div>
  );
}

function Last5Indicator({ results }: { results: ("W" | "L" | null)[] }) {
  if (results.length === 0) return null;
  return (
    <div className="flex gap-1.5 items-center">
      {results.map((r, i) => (
        <div
          key={i}
          className="w-7 h-7 rounded-lg flex items-center justify-center ios-num"
          style={{
            background:
              r === "W"
                ? "rgba(48,209,88,0.15)"
                : r === "L"
                ? "rgba(255,69,58,0.15)"
                : "rgba(142,142,147,0.12)",
            color:
              r === "W"
                ? "#30D158"
                : r === "L"
                ? "#FF453A"
                : "var(--label-tertiary)",
            border: `0.5px solid ${
              r === "W"
                ? "rgba(48,209,88,0.3)"
                : r === "L"
                ? "rgba(255,69,58,0.3)"
                : "rgba(142,142,147,0.2)"
            }`,
            fontSize: "11px",
            fontWeight: 700,
          }}
        >
          {r === "W" ? "✓" : r === "L" ? "✘" : "—"}
        </div>
      ))}
    </div>
  );
}

export function StatsBadge({ stats }: StatsBadgeProps) {
  const accPct = stats.accuracy !== null ? stats.accuracy : 0;
  const accColor =
    stats.accuracy === null
      ? "var(--label-tertiary)"
      : stats.accuracy >= 0.55
      ? "#30D158"
      : stats.accuracy >= 0.45
      ? "#FF9F0A"
      : "#FF453A";

  const streakColor =
    stats.current_streak.type === "W"
      ? "#30D158"
      : stats.current_streak.type === "L"
      ? "#FF453A"
      : "var(--label-tertiary)";

  return (
    <div
      className="ios-card rounded-[14px] p-4 animate-ios-up"
      style={{ background: "var(--bg-elevated)" }}
    >
      {/* Top row: accuracy ring + mini stats */}
      <div className="flex items-start gap-4">
        {/* Ring */}
        <ProbabilityRing
          value={accPct}
          label="Accuracy"
          size={72}
          color={accColor}
          strokeWidth={6}
        />

        {/* Stats grid */}
        <div className="flex-1 min-w-0 grid grid-cols-2 gap-y-2">
          <div>
            <p
              className="ios-headline font-bold ios-num"
              style={{ color: "var(--label-primary)" }}
            >
              {stats.hits}
              <span
                className="ios-subhead font-normal ios-secondary"
                style={{ color: "var(--label-secondary)" }}
              >
                /{stats.finished}
              </span>
            </p>
            <p className="ios-caption" style={{ color: "var(--label-tertiary)" }}>
              Aciertos evaluados
            </p>
          </div>
          <div>
            <p
              className="ios-headline font-bold ios-num"
              style={{ color: "var(--label-primary)" }}
            >
              {stats.brier !== null ? stats.brier.toFixed(4) : "—"}
            </p>
            <p className="ios-caption" style={{ color: "var(--label-tertiary)" }}>
              Brier (↓ mejor)
            </p>
          </div>
          <div>
            <p
              className="ios-headline font-bold"
              style={{ color: streakColor }}
            >
              {stats.current_streak.type
                ? `${stats.current_streak.length}${stats.current_streak.type}`
                : "—"}
            </p>
            <p className="ios-caption" style={{ color: "var(--label-tertiary)" }}>
              Racha actual
            </p>
          </div>
          <div>
            <p
              className="ios-headline font-bold ios-num"
              style={{ color: "var(--label-primary)" }}
            >
              {stats.total}
            </p>
            <p className="ios-caption" style={{ color: "var(--label-tertiary)" }}>
              Total predicciones
            </p>
          </div>
        </div>
      </div>

      {/* Last 5 */}
      {stats.last_5.length > 0 && (
        <div className="flex items-center justify-between mt-4 pt-4 ios-hairline-t">
          <p className="ios-footnote" style={{ color: "var(--label-secondary)" }}>
            Últimos 5
          </p>
          <Last5Indicator results={stats.last_5} />
        </div>
      )}

      {/* Breakdown by outcome */}
      <div className="flex gap-4 mt-4 pt-4 ios-hairline-t">
        {Object.entries(OUTCOME_LABELS).map(([key, { label, color }]) => {
          const data = stats.by_outcome[key] ?? {
            total: 0,
            hits: 0,
            accuracy: null,
          };
          return (
            <OutcomeRow
              key={key}
              label={label}
              data={data}
              color={color}
            />
          );
        })}
      </div>

      {/* Honest message */}
      {stats.finished === 0 && (
        <div
          className="mt-3 px-3 py-2 rounded-lg text-[11px] leading-relaxed"
          style={{
            background: "rgba(255,255,255,0.04)",
            color: "var(--label-secondary)",
          }}
        >
          Aún no hay predicciones <strong style={{ color: "var(--label-primary)" }}>live</strong>{" "}
          evaluadas. Los backtests se muestran pero no cuentan para la efectividad.
        </div>
      )}
    </div>
  );
}
