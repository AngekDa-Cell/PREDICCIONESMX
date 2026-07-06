"use client";
// iOS-style horizontal probability bar (inline, compact)
//
// Usage: <ProbabilityBars home={0.44} draw={0.30} away={0.26} />

interface ProbabilityBarsProps {
  home: number;
  draw: number;
  away: number;
  size?: "sm" | "md";
  showLabels?: boolean;
  className?: string;
}

function clamp(v: number) {
  return Math.max(0, Math.min(1, v ?? 0));
}

export function ProbabilityBars({
  home,
  draw,
  away,
  size = "md",
  showLabels = true,
  className = "",
}: ProbabilityBarsProps) {
  const h = size === "sm" ? "h-1" : "h-1.5";
  const labelSize = size === "sm" ? "text-[9px]" : "text-[10px]";
  const ph = clamp(home);
  const pd = clamp(draw);
  const pa = clamp(away);

  const rows = [
    { label: "Local", value: ph, color: "bg-[#30D158]" },
    { label: "Empate", value: pd, color: "bg-[rgba(142,142,147,0.7)]" },
    { label: "Visita", value: pa, color: "bg-[#0A84FF]" },
  ] as const;

  return (
    <div className={`space-y-2.5 ${className}`}>
      {rows.map(({ label, value, color }) => (
        <div key={label}>
          {showLabels && (
            <div className={`flex justify-between mb-1 ${labelSize} font-semibold uppercase tracking-wide`} style={{ color: "var(--label-secondary)" }}>
              <span>{label}</span>
              <span style={{ color: "var(--label-primary)" }}>{(value * 100).toFixed(1)}%</span>
            </div>
          )}
          <div className={`${h} w-full rounded-full overflow-hidden`} style={{ background: "rgba(255,255,255,0.08)" }}>
            <div
              className={`h-full ${color} transition-all duration-700 ease-out rounded-full`}
              style={{ width: `${(value * 100).toFixed(1)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
