"use client";

// VoteForm — formulario cliente para votar Local/Empate/Visita
// Mobile-first: botones enormes, feedback inmediato.

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import type { CrowdSummary } from "@/lib/db/votes";

interface Props {
  token: string;
  initialSummary: CrowdSummary | null;
  initialUserPick: "home" | "draw" | "away" | null;
  homeTeamShort: string;
  awayTeamShort: string;
  matchDate: string;
  canVote: boolean;       // false si ya empezó/terminó
  notVotingReason?: string;
}

const PICK_LABEL: Record<"home" | "draw" | "away", string> = {
  home: "Local",
  draw: "Empate",
  away: "Visita",
};
const PICK_EMOJI: Record<"home" | "draw" | "away", string> = {
  home: "🏠",
  draw: "🤝",
  away: "✈️",
};
const PICK_COLOR: Record<"home" | "draw" | "away", string> = {
  home: "var(--tint-green, #30D158)",
  draw: "var(--tint-orange, #FF9F0A)",
  away: "var(--tint-blue, #0A84FF)",
};

export function VoteForm({
  token,
  initialSummary,
  initialUserPick,
  homeTeamShort,
  awayTeamShort,
  matchDate,
  canVote,
  notVotingReason,
}: Props) {
  const router = useRouter();
  const [summary, setSummary] = useState<CrowdSummary | null>(initialSummary);
  const [userPick, setUserPick] = useState<"home" | "draw" | "away" | null>(
    initialUserPick,
  );
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const submitVote = async (pick: "home" | "draw" | "away") => {
    if (!canVote || submitting) return;
    setSubmitting(true);
    setErrorMsg(null);

    try {
      const res = await fetch(`/api/votes/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pick }),
      });
      const data = await res.json();
      if (!data.ok) {
        setErrorMsg(data.error || "Error registrando voto");
        return;
      }
      if (data.already_voted && data.existing_pick) {
        setUserPick(data.existing_pick);
      } else {
        setUserPick(pick);
      }
      if (data.summary) setSummary(data.summary);
      startTransition(() => router.refresh());
    } catch (err) {
      console.error(err);
      setErrorMsg("Sin conexión. Intenta de nuevo.");
    } finally {
      setSubmitting(false);
    }
  };

  const totalVotes = summary?.total ?? 0;
  const hasVotes = totalVotes > 0;

  return (
    <div className="space-y-6">
      {/* ─── Header del partido ─── */}
      <div
        className="ios-card text-center"
        style={{ padding: "20px 16px" }}
      >
        <p
          className="ios-caption mb-2"
          style={{ color: "var(--label-secondary)" }}
        >
          {matchDate}
        </p>
        <div className="flex items-center justify-center gap-3">
          <span
            className="ios-title-2 font-bold"
            style={{ color: "var(--label-primary)" }}
          >
            {homeTeamShort}
          </span>
          <span
            className="ios-title-3 font-bold"
            style={{ color: "var(--tint-blue)" }}
          >
            vs
          </span>
          <span
            className="ios-title-2 font-bold"
            style={{ color: "var(--label-primary)" }}
          >
            {awayTeamShort}
          </span>
        </div>
      </div>

      {/* ─── Botones de voto ─── */}
      {canVote ? (
        <div className="space-y-3">
          <p
            className="ios-callout font-semibold text-center"
            style={{ color: "var(--label-primary)" }}
          >
            {userPick ? "Tu voto" : "¿Quién gana?"}
          </p>

          <div className="grid grid-cols-1 gap-3">
            {(["home", "draw", "away"] as const).map((pick) => {
              const isSelected = userPick === pick;
              return (
                <button
                  key={pick}
                  onClick={() => submitVote(pick)}
                  disabled={submitting}
                  className="ios-card transition-all active:scale-[0.98]"
                  style={{
                    padding: "20px 16px",
                    background: isSelected
                      ? `color-mix(in srgb, ${PICK_COLOR[pick]} 18%, var(--bg-grouped-primary))`
                      : "var(--bg-grouped-primary)",
                    border: isSelected
                      ? `2px solid ${PICK_COLOR[pick]}`
                      : "0.5px solid rgba(255,255,255,0.05)",
                    opacity: submitting && !isSelected ? 0.5 : 1,
                    cursor: submitting ? "wait" : "pointer",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span style={{ fontSize: 28 }}>{PICK_EMOJI[pick]}</span>
                      <div className="text-left">
                        <p
                          className="ios-title-3 font-bold"
                          style={{ color: PICK_COLOR[pick] }}
                        >
                          {PICK_LABEL[pick]}
                          {pick === "home" && ` · ${homeTeamShort}`}
                          {pick === "away" && ` · ${awayTeamShort}`}
                        </p>
                        {summary && hasVotes && (
                          <p
                            className="ios-footnote mt-1 ios-num"
                            style={{ color: "var(--label-tertiary)" }}
                          >
                            {pick === "home" &&
                              `${summary.home} de ${summary.total} (${(summary.home_pct * 100).toFixed(0)}%)`}
                            {pick === "draw" &&
                              `${summary.draw} de ${summary.total} (${(summary.draw_pct * 100).toFixed(0)}%)`}
                            {pick === "away" &&
                              `${summary.away} de ${summary.total} (${(summary.away_pct * 100).toFixed(0)}%)`}
                          </p>
                        )}
                      </div>
                    </div>
                    {isSelected && (
                      <span
                        className="ios-headline font-bold"
                        style={{ color: PICK_COLOR[pick] }}
                      >
                        ✓
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {userPick && (
            <p
              className="ios-footnote text-center"
              style={{ color: "var(--label-secondary)" }}
            >
              Ya votaste. Vuelve a tocar otro botón si quieres cambiar tu voto.
            </p>
          )}
          {errorMsg && (
            <p
              className="ios-footnote text-center"
              style={{ color: "var(--tint-red, #FF453A)" }}
            >
              {errorMsg}
            </p>
          )}
        </div>
      ) : (
        <div
          className="ios-card text-center"
          style={{ padding: "20px 16px" }}
        >
          <p
            className="ios-callout font-semibold"
            style={{ color: "var(--label-secondary)" }}
          >
            🔒 {notVotingReason || "Votación cerrada"}
          </p>
          <p
            className="ios-footnote mt-2"
            style={{ color: "var(--label-tertiary)" }}
          >
            Solo se puede votar antes del partido.
          </p>
        </div>
      )}

      {/* ─── Resumen del crowd ─── */}
      {hasVotes ? (
        <div
          className="ios-card"
          style={{ padding: "20px 16px" }}
        >
          <p
            className="ios-caption mb-3"
            style={{ color: "var(--label-secondary)" }}
          >
            Voto de la banda
          </p>
          <div className="space-y-2">
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
              return (
                <div key={pick}>
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className="ios-footnote font-semibold"
                      style={{ color: PICK_COLOR[pick] }}
                    >
                      {PICK_LABEL[pick]}
                    </span>
                    <span
                      className="ios-footnote ios-num"
                      style={{ color: "var(--label-secondary)" }}
                    >
                      {count} · {(value * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div
                    style={{
                      height: 8,
                      borderRadius: 4,
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
          </div>
          <p
            className="ios-footnote mt-3 text-center"
            style={{ color: "var(--label-tertiary)" }}
          >
            {totalVotes} {totalVotes === 1 ? "voto" : "votos"} totales
          </p>
        </div>
      ) : (
        !userPick && (
          <div
            className="ios-card text-center"
            style={{ padding: "20px 16px" }}
          >
            <p
              className="ios-callout font-semibold"
              style={{ color: "var(--label-primary)" }}
            >
              Sé el primero en votar
            </p>
            <p
              className="ios-footnote mt-2"
              style={{ color: "var(--label-tertiary)" }}
            >
              Nadie ha opinado aún sobre este partido.
            </p>
          </div>
        )
      )}

      {/* ─── Footer discreto ─── */}
      <p
        className="ios-footnote text-center"
        style={{ color: "var(--label-tertiary)" }}
      >
        Quinielas.lol · Voto libre, anónimo y 1 por persona
      </p>
    </div>
  );
}
