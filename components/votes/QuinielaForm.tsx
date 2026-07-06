"use client";

// QuinielaForm — Vista estilo BOLETO DE LOTERÍA (Progol).
//
// Diseño:
// - Tabla con cuadrícula estilo boleto oficial.
// - Numeración de partidos (1, 2, 3...).
// - Sin fecha/hora por partido (eso vive en /calendario).
// - Círculos marcables para Local / Empate / Visita (○ → ●).
// - Header tipo "BOLETO OFICIAL · JORNADA N".
// - Footer con contador X/N + botón "GUARDAR BOLETO".
//
// Estado:
// - localPicks: { [fixture_id]: 'home'|'draw'|'away' } — picks en esta sesión.
// - isLocked: true si la jornada ya empezó/terminó (modo lectura con crowd bars).
// - submitting / errorMsg / savedAt: manejo del POST batch.

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import type { FixtureWithPrediction, CrowdSummary, Pick } from "@/lib/db";

interface JornadaOption {
  season_id: number;
  matchday: number;
  label: string;
  first_kickoff: string;
  match_count: number;
  has_started: boolean;
}

interface Props {
  currentJornada: { season_id: number; matchday: number; label: string };
  jornadas: JornadaOption[];
  partidos: Array<FixtureWithPrediction & {
    crowd_summary: CrowdSummary | null;
  }>;
  initialPicks: Record<number, Pick>;
  hasVotedBefore?: boolean;  // true si el usuario YA votó antes (cookie ligera)
  isLocked: boolean;
}

const PICK_LABEL: Record<Pick, string> = {
  home: "L",
  draw: "E",
  away: "V",
};
const PICK_LONG: Record<Pick, string> = {
  home: "Local",
  draw: "Empate",
  away: "Visita",
};
const PICK_COLOR: Record<Pick, string> = {
  home: "#16A34A",  // verde oscuro tipo Progol
  draw: "#D97706",  // ámbar
  away: "#2563EB",  // azul
};
const PICK_BG: Record<Pick, string> = {
  home: "#DCFCE7",
  draw: "#FEF3C7",
  away: "#DBEAFE",
};

export function QuinielaForm({
  currentJornada,
  jornadas,
  partidos,
  initialPicks,
  hasVotedBefore = false,
  isLocked,
}: Props) {
  const router = useRouter();

  const [localPicks, setLocalPicks] = useState<Record<number, Pick>>(
    () => ({ ...initialPicks }),
  );
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const onPick = (fixtureId: number, pick: Pick) => {
    if (isLocked || submitting) return;
    setErrorMsg(null);
    setLocalPicks((prev) => ({ ...prev, [fixtureId]: pick }));
  };

  const onClearPick = (fixtureId: number) => {
    if (isLocked || submitting) return;
    setErrorMsg(null);
    setLocalPicks((prev) => {
      const next = { ...prev };
      delete next[fixtureId];
      return next;
    });
  };

  const picksCount = Object.keys(localPicks).length;
  const totalMatches = partidos.length;
  const isDirty =
    JSON.stringify(localPicks) !== JSON.stringify(initialPicks);
  // El % crowd solo se muestra después de que el usuario haya guardado
  // su primera votación. Mientras no haya picks guardados, se mantiene
  // "oculto" para evitar sesgo social antes de votar.
// Consideramos "ya votó" si:
//   - hay picks iniciales (initialPicks no vacío), o
//   - la cookie hasVotedBefore viene en true (seteada al guardar)
  const userHasVoted =
    Object.keys(initialPicks).length > 0 || hasVotedBefore;

  const save = async () => {
    if (isLocked || submitting) return;
    setErrorMsg(null);
    setSubmitting(true);
    try {
      const body = {
        jornada: {
          season_id: currentJornada.season_id,
          matchday: currentJornada.matchday,
        },
        picks: Object.entries(localPicks).map(([fid, pick]) => ({
          fixture_id: Number(fid),
          pick,
        })),
      };
      const res = await fetch("/api/quiniela", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!data.ok) {
        setErrorMsg(data.error || "Error guardando quiniela");
        return;
      }
      setSavedAt(new Date().toISOString());
      startTransition(() => router.refresh());
    } catch (err) {
      console.error(err);
      setErrorMsg("Sin conexión. Intenta de nuevo.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* ─── Selector de jornada (chips) ─── */}
      <div>
        <p
          className="ios-caption mb-2"
          style={{ color: "var(--label-secondary)" }}
        >
          JORNADAS DISPONIBLES
        </p>
        <div
          style={{
            display: "flex",
            gap: 8,
            overflowX: "auto",
            paddingBottom: 4,
            scrollbarWidth: "none",
          }}
          className="cp-hide-scrollbar"
        >
          {jornadas.map((j) => {
            const isCurrent =
              j.season_id === currentJornada.season_id &&
              j.matchday === currentJornada.matchday;
            return (
              <a
                key={`${j.season_id}:${j.matchday}`}
                href={
                  j.has_started
                    ? "#"
                    : `/votacion?season_id=${j.season_id}&matchday=${j.matchday}`
                }
                onClick={(e) => {
                  if (j.has_started) e.preventDefault();
                }}
                style={{
                  flexShrink: 0,
                  padding: "8px 14px",
                  borderRadius: 999,
                  background: isCurrent
                    ? "var(--gradient-hero)"
                    : "var(--bg-elevated)",
                  border: isCurrent
                    ? "1px solid transparent"
                    : "1px solid var(--hairline)",
                  color: isCurrent
                    ? "white"
                    : "var(--label-primary)",
                  fontSize: "0.8rem",
                  fontWeight: 700,
                  textDecoration: "none",
                  opacity: j.has_started ? 0.5 : 1,
                  cursor: j.has_started ? "not-allowed" : "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                {j.label}
                {j.has_started && " 🔒"}
              </a>
            );
          })}
        </div>
      </div>

      {/* ─── BOLETO OFICIAL ─── */}
      <div
        style={{
          background: "#FFFFFF",
          color: "#0F172A",
          border: "2px solid #0F172A",
          borderRadius: 4,
          overflow: "hidden",
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        }}
      >
        {/* Header del boleto */}
        <div
          style={{
            background: "#0F172A",
            color: "#FFFFFF",
            padding: "12px 16px",
            borderBottom: "2px solid #0F172A",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <div>
            <p
              style={{
                fontSize: "0.65rem",
                fontWeight: 800,
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                color: "#94A3B8",
                margin: 0,
              }}
            >
              Quiniela MX · Quinielas.lol
            </p>
            <h2
              style={{
                fontSize: "1.1rem",
                fontWeight: 900,
                letterSpacing: "-0.01em",
                color: "#FFFFFF",
                margin: 0,
                textTransform: "uppercase",
              }}
            >
              BOLETO OFICIAL · {currentJornada.label}
            </h2>
          </div>
          <div
            style={{
              padding: "4px 10px",
              background: isLocked ? "#FEE2E2" : "#DCFCE7",
              color: isLocked ? "#991B1B" : "#166534",
              borderRadius: 4,
              fontSize: "0.7rem",
              fontWeight: 800,
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              border: `1px solid ${isLocked ? "#FCA5A5" : "#86EFAC"}`,
            }}
          >
            {isLocked ? "🔒 Cerrada" : "Abierta"}
          </div>
        </div>

        {/* Tabla de partidos */}
        <div
          style={{
            overflowX: "auto",
          }}
        >
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.85rem",
            }}
          >
            <thead>
              <tr
                style={{
                  background: "#F1F5F9",
                  borderBottom: "2px solid #0F172A",
                }}
              >
                <th
                  style={{
                    padding: "8px 6px",
                    width: 32,
                    textAlign: "center",
                    fontWeight: 800,
                    fontSize: "0.7rem",
                    color: "#475569",
                    borderRight: "1px solid #CBD5E1",
                  }}
                >
                  #
                </th>
                <th
                  style={{
                    padding: "8px 10px",
                    textAlign: "left",
                    fontWeight: 800,
                    fontSize: "0.7rem",
                    color: "#475569",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    borderRight: "1px solid #CBD5E1",
                  }}
                >
                  Partido
                </th>
                <th
                  colSpan={3}
                  style={{
                    padding: "8px 6px",
                    textAlign: "center",
                    fontWeight: 800,
                    fontSize: "0.7rem",
                    color: "#475569",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Pronóstico
                </th>
              </tr>
            </thead>
            <tbody>
              {partidos.map((f, idx) => {
                const userPick = localPicks[f.id];
                const summary = f.crowd_summary;
                const total = summary?.total ?? 0;
                const isLast = idx === partidos.length - 1;
                return (
                  <tr
                    key={f.id}
                    style={{
                      background: idx % 2 === 0 ? "#FFFFFF" : "#FAFAFA",
                      borderBottom: isLast
                        ? "none"
                        : "1px solid #E2E8F0",
                    }}
                  >
                    {/* Número */}
                    <td
                      style={{
                        padding: "10px 6px",
                        textAlign: "center",
                        fontWeight: 900,
                        fontSize: "0.95rem",
                        color: "#0F172A",
                        borderRight: "1px solid #CBD5E1",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {idx + 1}
                    </td>

                    {/* Partido */}
                    <td
                      style={{
                        padding: "10px 10px",
                        borderRight: "1px solid #CBD5E1",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          fontWeight: 700,
                          fontSize: "0.85rem",
                          color: "#0F172A",
                        }}
                      >
                        <span
                          style={{
                            flex: 1,
                            textAlign: "right",
                          }}
                        >
                          {f.home_team_short || f.home_team_name}
                        </span>
                        <span
                          style={{
                            color: "#94A3B8",
                            fontWeight: 600,
                            fontSize: "0.7rem",
                            padding: "0 4px",
                          }}
                        >
                          vs
                        </span>
                        <span style={{ flex: 1 }}>
                          {f.away_team_short || f.away_team_name}
                        </span>
                      </div>
                      {userHasVoted && summary && total > 0 && !isLocked && (
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            fontSize: "0.6rem",
                            color: "#64748B",
                            marginTop: 4,
                            fontWeight: 600,
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          <span style={{ color: PICK_COLOR.home }}>
                            L {Math.round(summary.home_pct * 100)}%
                          </span>
                          <span style={{ color: PICK_COLOR.draw }}>
                            E {Math.round(summary.draw_pct * 100)}%
                          </span>
                          <span style={{ color: PICK_COLOR.away }}>
                            V {Math.round(summary.away_pct * 100)}%
                          </span>
                        </div>
                      )}
                    </td>

                    {/* Círculos L / E / V */}
                    {(["home", "draw", "away"] as const).map((pick) => {
                      const isSelected = userPick === pick;
                      const isLastCol = pick === "away";
                      return (
                        <td
                          key={pick}
                          style={{
                            padding: "6px 4px",
                            textAlign: "center",
                            borderRight: isLastCol
                              ? "none"
                              : "1px solid #E2E8F0",
                            width: 48,
                          }}
                        >
                          <button
                            onClick={() => onPick(f.id, pick)}
                            disabled={isLocked || submitting}
                            aria-label={`${PICK_LONG[pick]} para ${f.home_team_name} vs ${f.away_team_name}`}
                            style={{
                              width: 32,
                              height: 32,
                              borderRadius: "50%",
                              border: `2px solid ${isSelected ? PICK_COLOR[pick] : "#CBD5E1"}`,
                              background: isSelected
                                ? PICK_COLOR[pick]
                                : "#FFFFFF",
                              cursor:
                                isLocked || submitting
                                  ? "not-allowed"
                                  : "pointer",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              padding: 0,
                              transition: "all 0.15s ease",
                              opacity: isLocked ? 0.5 : 1,
                            }}
                          >
                            {isSelected && (
                              <span
                                style={{
                                  color: "#FFFFFF",
                                  fontSize: "1rem",
                                  fontWeight: 900,
                                  lineHeight: 1,
                                }}
                              >
                                ✓
                              </span>
                            )}
                          </button>
                          <div
                            style={{
                              fontSize: "0.6rem",
                              fontWeight: 800,
                              color: isSelected
                                ? PICK_COLOR[pick]
                                : "#94A3B8",
                              marginTop: 2,
                              letterSpacing: "0.05em",
                            }}
                          >
                            {PICK_LABEL[pick]}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer del boleto */}
        {!isLocked && (
          <div
            style={{
              borderTop: "2px solid #0F172A",
              padding: "12px 16px",
              background: "#F8FAFC",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 10,
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              <div>
                <p
                  style={{
                    fontSize: "0.95rem",
                    fontWeight: 800,
                    color: "#0F172A",
                    margin: 0,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {picksCount}/{totalMatches}{" "}
                  <span style={{ fontWeight: 500, color: "#64748B" }}>
                    pronósticos
                  </span>
                </p>
                <p
                  style={{
                    fontSize: "0.7rem",
                    color: "#64748B",
                    margin: 0,
                    marginTop: 2,
                  }}
                >
                  {savedAt
                    ? `✓ Guardado ${new Date(savedAt).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" })}`
                    : isDirty
                    ? "Cambios sin guardar"
                    : "Todo guardado"}
                </p>
              </div>
              {picksCount > 0 && (
                <button
                  onClick={() => setLocalPicks({})}
                  disabled={submitting}
                  style={{
                    fontSize: "0.7rem",
                    color: "#64748B",
                    background: "transparent",
                    border: "none",
                    textDecoration: "underline",
                    cursor: "pointer",
                    padding: 0,
                  }}
                >
                  Limpiar todo
                </button>
              )}
            </div>
            {errorMsg && (
              <p
                style={{
                  fontSize: "0.75rem",
                  color: "#B91C1C",
                  textAlign: "center",
                  marginBottom: 8,
                }}
              >
                {errorMsg}
              </p>
            )}
            <button
              onClick={save}
              disabled={submitting || picksCount === 0}
              style={{
                width: "100%",
                padding: "14px 16px",
                fontSize: "0.95rem",
                fontWeight: 900,
                letterSpacing: "0.05em",
                textTransform: "uppercase",
                background: picksCount === 0 ? "#CBD5E1" : "#0F172A",
                color: picksCount === 0 ? "#94A3B8" : "#FFFFFF",
                border: "2px solid #0F172A",
                borderRadius: 4,
                cursor: picksCount === 0 ? "not-allowed" : "pointer",
                opacity: submitting ? 0.7 : 1,
                transition: "all 0.15s ease",
              }}
            >
              {submitting ? "Guardando..." : "💾 Guardar boleto"}
            </button>
          </div>
        )}

        {/* Modo lectura: solo crowd bars */}
        {isLocked && (
          <div
            style={{
              borderTop: "2px solid #0F172A",
              padding: "12px 16px",
              background: "#F8FAFC",
              textAlign: "center",
            }}
          >
            <p
              style={{
                fontSize: "0.75rem",
                color: "#64748B",
                margin: 0,
              }}
            >
              🔒 La jornada ya cerró. No se puede modificar la quiniela.
            </p>
          </div>
        )}
      </div>

      {/* Footnote */}
      <p
        style={{
          fontSize: "0.65rem",
          color: "var(--label-tertiary)",
          textAlign: "center",
          paddingTop: 4,
          paddingBottom: 8,
        }}
      >
        1 boleto por persona (cookie anti-spam) · Editá mientras la jornada no empiece
      </p>
    </div>
  );
}