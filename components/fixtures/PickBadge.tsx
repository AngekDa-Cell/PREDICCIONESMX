"use client";
// PickBadge — shows the model's pick with semantic color
// Usage: <PickBadge outcome="home_win" confidence={0.62} />

interface PickBadgeProps {
  outcome: string | null;  // "home_win" | "away_win" | "draw" | null
  confidence?: number | null;
  size?: "sm" | "md";
  showConfidence?: boolean;
}

const LABEL: Record<string, string> = {
  home_win: "Local",
  away_win: "Visita",
  draw: "Empate",
};

const COLOR: Record<string, "green" | "blue" | "neutral"> = {
  home_win: "green",
  away_win: "blue",
  draw: "neutral",
};

export function PickBadge({
  outcome,
  confidence,
  size = "md",
  showConfidence = false,
}: PickBadgeProps) {
  if (!outcome) return null;

  const label = LABEL[outcome] ?? outcome;
  const color = COLOR[outcome] ?? "neutral";

  const confPct =
    confidence !== null && confidence !== undefined
      ? `${(confidence * 100).toFixed(0)}%`
      : null;

  return (
    <span
      className={`ios-badge ios-badge-${color} ${size === "sm" ? "text-[9px] px-1.5" : "text-[11px]"}`}
    >
      {label}
      {showConfidence && confPct && (
        <span className="opacity-70 ml-0.5">{confPct}</span>
      )}
    </span>
  );
}
