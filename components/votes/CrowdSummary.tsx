"use client";

// CrowdSummary — widget para mostrar el resumen del voto crowd
// en /partido/[id]. NO permite votar (eso es /voto/[token]).

import { useState } from "react";
import type { CrowdSummary } from "@/lib/db/votes";
import { CopyVoteLink } from "./CopyVoteLink";

interface Props {
  fixtureId: number;
  token: string;
  summary: CrowdSummary | null;
  votingEnabled: boolean;
}

const PICK_LABEL: Record<"home" | "draw" | "away", string> = {
  home: "Local",
  draw: "Empate",
  away: "Visita",
};
const PICK_COLOR: Record<"home" | "draw" | "away", string> = {
  home: "#30D158",
  draw: "#FF9F0A",
  away: "#0A84FF",
};

export function CrowdSummary({ token, summary, votingEnabled }: Props) {
  const [showShare, setShowShare] = useState(false);
  const total = summary?.total ?? 0;
  const hasVotes = total > 0;

  return (
    <div
      className="ios-card"
      style={{
        padding: "20px",
        background: "var(--bg-grouped-secondary)",
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <p
          className="ios-callout font-semibold"
          style={{ color: "var(--label-primary)" }}
        >
          👥 Voto de la banda
        </p>
        {votingEnabled && (
          <button
            onClick={() => setShowShare((s) => !s)}
            className="ios-footnote font-semibold"
            style={{
              color: "var(--tint-blue)",
              background: "transparent",
              border: 0,
              padding: "4px 8px",
            }}
          >
            {showShare ? "Ocultar" : "Compartir"}
          </button>
        )}
      </div>

      {hasVotes ? (
        <div className="space-y-2 mb-3">
          {(["home", "draw", "away"] as const).map((pick) => {
            const value =
              pick === "home"
                ? summary!.home_pct
                : pick === "draw"
                ? summary!.draw_pct
                : summary!.away_pct;
            const count =
              pick === "home"
                ? summary!.home
                : pick === "draw"
                ? summary!.draw
                : summary!.away;
            const isLeader =
              count > 0 && count === Math.max(summary!.home, summary!.draw, summary!.away);
            return (
              <div key={pick}>
                <div className="flex items-center justify-between mb-1">
                  <span
                    className="ios-footnote font-semibold"
                    style={{
                      color: PICK_COLOR[pick],
                      opacity: isLeader ? 1 : 0.6,
                    }}
                  >
                    {PICK_LABEL[pick]}
                  </span>
                  <span
                    className="ios-footnote ios-num"
                    style={{
                      color: isLeader ? PICK_COLOR[pick] : "var(--label-secondary)",
                      fontWeight: isLeader ? 600 : 400,
                    }}
                  >
                    {(value * 100).toFixed(0)}% · {count}
                  </span>
                </div>
                <div
                  style={{
                    height: 6,
                    borderRadius: 3,
                    background: "rgba(255,255,255,0.05)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${value * 100}%`,
                      height: "100%",
                      background: PICK_COLOR[pick],
                      transition: "width 0.4s ease",
                    }}
                  />
                </div>
              </div>
            );
          })}
          <p
            className="ios-footnote text-center mt-3"
            style={{ color: "var(--label-tertiary)" }}
          >
            {total} {total === 1 ? "voto" : "votos"} · no afecta la predicción
          </p>
        </div>
      ) : (
        <p
          className="ios-footnote mb-3 text-center"
          style={{ color: "var(--label-secondary)" }}
        >
          Nadie ha votado aún.
          {votingEnabled && " Sé el primero."}
        </p>
      )}

      {showShare && votingEnabled && (
        <CopyVoteLink token={token} />
      )}
    </div>
  );
}
