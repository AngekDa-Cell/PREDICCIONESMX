"use client";
// MatchClock — relative time display: "en 2 días", "hoy 8:00pm", "mañana"
import { useMemo } from "react";

interface MatchClockProps {
  startingAt: string;
  status?: string | null;
  compact?: boolean;
}

function formatRelative(date: Date): string {
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

  const timeStr = date.toLocaleTimeString("es-MX", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Mexico_City",
  });

  if (diffDays < 0) return "Finalizado";
  if (diffDays === 0) return `Hoy · ${timeStr}`;
  if (diffDays === 1) return `Mañana · ${timeStr}`;
  if (diffDays <= 6) return `En ${diffDays} días`;
  return date.toLocaleDateString("es-MX", {
    day: "numeric",
    month: "short",
  });
}

export function MatchClock({ startingAt, status, compact = false }: MatchClockProps) {
  const date = useMemo(() => new Date(startingAt), [startingAt]);
  const isFinished = status === "FINISHED" || status === "FT";

  if (isFinished) {
    return (
      <span className="ios-caption" style={{ color: "var(--label-tertiary)" }}>
        Finalizado
      </span>
    );
  }

  const text = compact
    ? date.toLocaleDateString("es-MX", { day: "numeric", month: "short" })
    : formatRelative(date);

  return (
    <span className="ios-footnote" style={{ color: "var(--label-secondary)" }}>
      {text}
    </span>
  );
}
