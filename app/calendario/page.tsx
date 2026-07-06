/**
 * /calendario — Vista calendario mensual con grid + lista de partidos.
 *
 * Diferencia con /partidos:
 * - /partidos: lista plana agrupada por jornada (elige tu quiniela)
 * - /calendario: grid mensual tipo Google Calendar + partidos del mes por día
 *
 * Features:
 * - Grid 7×N (L M X J V S D) del mes
 * - Selector de mes ◀ ▶ (default: mes del próximo partido)
 * - Días con partidos resaltados con dot azul
 * - Debajo: lista de partidos del mes agrupados por día
 * - Click en día del grid (futuro: filtra la lista a ese día)
 */

import Link from "next/link";
import { BackButton } from "@/components/layout";
import {
  getUpcomingFixtures,
  getFixturesInRange,
  getMatchdayOrdinalByDate,
  type FixtureWithPrediction,
} from "@/lib/db";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { PickBadge } from "@/components/fixtures/PickBadge";
import { MatchClock } from "@/components/fixtures/MatchClock";

export const dynamic = "force-dynamic";

// Locale-aware month/day names
const MONTHS_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const WEEKDAYS_ES = ["L", "M", "X", "J", "V", "S", "D"]; // L-D
const WEEKDAYS_ES_LONG = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

const MONTHS_ES_CAP = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

interface PageProps {
  searchParams: { y?: string; m?: string };
}

export default function CalendarioPage({ searchParams }: PageProps) {
  // Default: mes del primer partido próximo
  const upcoming = getUpcomingFixtures(60, 200);
  const firstUpcoming = upcoming[0];
  const today = new Date();
  const defaultYear = firstUpcoming
    ? new Date(firstUpcoming.starting_at).getUTCFullYear()
    : today.getUTCFullYear();
  const defaultMonth = firstUpcoming
    ? new Date(firstUpcoming.starting_at).getUTCMonth()
    : today.getUTCMonth();

  // Parse search params (y = year, m = month 0-11)
  const y = searchParams.y ? parseInt(searchParams.y, 10) : defaultYear;
  const m = searchParams.m !== undefined ? parseInt(searchParams.m, 10) : defaultMonth;

  // Calcular primer día del mes y rango (lunes a domingo)
  const firstOfMonth = new Date(Date.UTC(y, m, 1));
  const lastOfMonth = new Date(Date.UTC(y, m + 1, 0)); // día 0 del mes sig = último día

  // Ajustar para que la semana empiece en lunes (0 = lunes)
  const firstWeekday = (firstOfMonth.getUTCDay() + 6) % 7; // 0 si lunes
  const gridStart = new Date(firstOfMonth);
  gridStart.setUTCDate(gridStart.getUTCDate() - firstWeekday);

  const gridEnd = new Date(gridStart);
  gridEnd.setUTCDate(gridEnd.getUTCDate() + 41); // 6 filas × 7 días

  // Fetch fixtures en el rango del grid (incluye días fuera del mes pero visibles)
  const fixtures = getFixturesInRange(
    gridStart.toISOString().slice(0, 10),
    gridEnd.toISOString().slice(0, 10),
  );

  // Index fixtures por día del mes
  const fixturesByDay = new Map<string, FixtureWithPrediction[]>();
  for (const f of fixtures) {
    const d = f.starting_at.slice(0, 10); // YYYY-MM-DD
    if (!fixturesByDay.has(d)) fixturesByDay.set(d, []);
    fixturesByDay.get(d)!.push(f);
  }

  // Generar celdas del grid
  const cells: { date: Date; inMonth: boolean; iso: string }[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(gridStart);
    d.setUTCDate(d.getUTCDate() + i);
    cells.push({
      date: d,
      inMonth: d.getUTCMonth() === m,
      iso: d.toISOString().slice(0, 10),
    });
  }

  // Partidos del mes visible (para lista inferior)
  const monthFixtures = fixtures
    .filter((f) => {
      const d = new Date(f.starting_at);
      return d.getUTCFullYear() === y && d.getUTCMonth() === m;
    })
    .sort(
      (a, b) =>
        new Date(a.starting_at).getTime() - new Date(b.starting_at).getTime(),
    );

  // Agrupar por día (solo días con partidos)
  const monthByDay = new Map<string, FixtureWithPrediction[]>();
  for (const f of monthFixtures) {
    const d = f.starting_at.slice(0, 10);
    if (!monthByDay.has(d)) monthByDay.set(d, []);
    monthByDay.get(d)!.push(f);
  }

  // Navegación prev/next
  const prevY = m === 0 ? y - 1 : y;
  const prevM = m === 0 ? 11 : m - 1;
  const nextY = m === 11 ? y + 1 : y;
  const nextM = m === 11 ? 0 : m + 1;
  const isCurrentMonth =
    y === today.getUTCFullYear() && m === today.getUTCMonth();
  const todayISO = today.toISOString().slice(0, 10);

  return (
    <div className="space-y-5 cp-animate-up">
      {/* ─── Page header ─── */}
      <header className="pb-2">
        <BackButton href="/" label="Inicio" />
        <h1
          style={{
            fontSize: "1.5rem",
            fontWeight: 800,
            letterSpacing: "-0.02em",
            color: "var(--label-primary)",
          }}
        >
          Calendario
        </h1>
        <p
          style={{
            fontSize: "0.875rem",
            color: "var(--label-secondary)",
            marginTop: 4,
          }}
        >
          {monthFixtures.length} partido{monthFixtures.length !== 1 ? "s" : ""} en{" "}
          {MONTHS_ES_CAP[m]} {y}
        </p>
      </header>

      {/* ─── Month switcher ─── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--bg-elevated)",
          border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-md)",
          padding: "12px 16px",
        }}
      >
        <Link
          href={`/calendario?y=${prevY}&m=${prevM}`}
          aria-label="Mes anterior"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 36,
            height: 36,
            borderRadius: "var(--radius-sm)",
            background: "var(--bg-elevated-2)",
            color: "var(--tint-blue)",
            fontSize: "1.25rem",
          }}
        >
          ‹
        </Link>
        <h2
          style={{
            fontSize: "1rem",
            fontWeight: 700,
            letterSpacing: "-0.01em",
            color: "var(--label-primary)",
            textTransform: "capitalize",
          }}
        >
          {MONTHS_ES_CAP[m]} {y}
        </h2>
        <Link
          href={`/calendario?y=${nextY}&m=${nextM}`}
          aria-label="Mes siguiente"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 36,
            height: 36,
            borderRadius: "var(--radius-sm)",
            background: "var(--bg-elevated-2)",
            color: "var(--tint-blue)",
            fontSize: "1.25rem",
          }}
        >
          ›
        </Link>
      </div>

      {/* ─── Calendar grid ─── */}
      <div
        style={{
          background: "var(--bg-elevated)",
          border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-md)",
          padding: "12px",
        }}
      >
        {/* Weekday headers */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(7, 1fr)",
            gap: 4,
            marginBottom: 8,
          }}
        >
          {WEEKDAYS_ES.map((w, i) => (
            <div
              key={w}
              title={WEEKDAYS_ES_LONG[i]}
              style={{
                textAlign: "center",
                fontSize: "0.7rem",
                fontWeight: 700,
                color: "var(--label-tertiary)",
                textTransform: "uppercase",
                letterSpacing: "0.5px",
                padding: "4px 0",
              }}
            >
              {w}
            </div>
          ))}
        </div>

        {/* Day cells */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(7, 1fr)",
            gap: 4,
          }}
        >
          {cells.map((c) => {
            const dayFixtures = fixturesByDay.get(c.iso) ?? [];
            const hasFixtures = dayFixtures.length > 0;
            const isToday = c.iso === todayISO;

            return (
              <div
                key={c.iso}
                style={{
                  aspectRatio: "1 / 1",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "flex-start",
                  padding: "6px 2px",
                  borderRadius: "var(--radius-sm)",
                  background: isToday
                    ? "var(--tint-blue-bg)"
                    : hasFixtures && c.inMonth
                    ? "rgba(71, 129, 255, 0.06)"
                    : "transparent",
                  border: isToday
                    ? "1px solid var(--tint-blue)"
                    : hasFixtures && c.inMonth
                    ? "1px solid rgba(71,129,255,0.18)"
                    : "1px solid transparent",
                  opacity: c.inMonth ? 1 : 0.3,
                  position: "relative",
                  transition: "all var(--dur-fast) var(--ease-ios)",
                }}
              >
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: isToday ? 700 : 500,
                    color: isToday
                      ? "var(--tint-blue)"
                      : c.inMonth
                      ? "var(--label-primary)"
                      : "var(--label-tertiary)",
                  }}
                >
                  {c.date.getUTCDate()}
                </span>
                {hasFixtures && (
                  <div
                    style={{
                      display: "flex",
                      gap: 2,
                      marginTop: 4,
                      flexWrap: "wrap",
                      justifyContent: "center",
                    }}
                  >
                    {dayFixtures.slice(0, 3).map((f) => (
                      <span
                        key={f.id}
                        style={{
                          width: 5,
                          height: 5,
                          borderRadius: "50%",
                          background: isToday ? "var(--tint-blue)" : "var(--tint-purple)",
                        }}
                      />
                    ))}
                    {dayFixtures.length > 3 && (
                      <span
                        style={{
                          fontSize: "0.5rem",
                          fontWeight: 700,
                          color: "var(--label-tertiary)",
                          lineHeight: 1,
                        }}
                      >
                        +{dayFixtures.length - 3}
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Leyenda */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginTop: 12,
            padding: "8px 4px",
            fontSize: "0.65rem",
            color: "var(--label-tertiary)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "var(--tint-purple)",
              }}
            />
            Con partido
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "var(--tint-blue)",
              }}
            />
            Hoy
          </div>
        </div>
      </div>

      {/* ─── Month fixtures list ─── */}
      {monthFixtures.length === 0 ? (
        <EmptyState month={MONTHS_ES_CAP[m]} year={y} />
      ) : (
        <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {[...monthByDay.entries()].map(([day, dayFixtures]) => {
            const d = new Date(day);
            const ord = getMatchdayOrdinalByDate(
              dayFixtures[0].season_id,
              dayFixtures[0].matchday,
              dayFixtures[0].starting_at,
            );
            const dateLabel = d.toLocaleDateString("es-MX", {
              weekday: "long",
              day: "2-digit",
            });

            return (
              <DayGroup
                key={day}
                dateLabel={dateLabel}
                jornadaOrd={ord}
                fixtures={dayFixtures}
              />
            );
          })}
        </section>
      )}
    </div>
  );
}

// ─── Day group (lista de partidos de un día) ─────────────────────────────
function DayGroup({
  dateLabel,
  jornadaOrd,
  fixtures,
}: {
  dateLabel: string;
  jornadaOrd: number | null;
  fixtures: FixtureWithPrediction[];
}) {
  return (
    <div>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 8,
          paddingLeft: 4,
        }}
      >
        <h3
          style={{
            fontSize: "0.7rem",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            color: "var(--label-tertiary)",
          }}
        >
          {dateLabel}
        </h3>
        {jornadaOrd !== null && jornadaOrd > 0 && (
          <span
            style={{
              fontSize: "0.65rem",
              fontWeight: 600,
              color: "var(--tint-blue)",
              background: "var(--tint-blue-bg)",
              padding: "2px 8px",
              borderRadius: "var(--radius-pill)",
            }}
          >
            J{jornadaOrd}
          </span>
        )}
      </header>

      <div
        style={{
          background: "var(--bg-elevated)",
          border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-md)",
          overflow: "hidden",
        }}
      >
        {fixtures.map((f, i) => (
          <FixtureCompact key={f.id} fixture={f} showHairline={i > 0} />
        ))}
      </div>
    </div>
  );
}

// ─── Fixture row compacto para la lista del mes ─────────────────────────
function FixtureCompact({
  fixture,
  showHairline,
}: {
  fixture: FixtureWithPrediction;
  showHairline: boolean;
}) {
  const f = fixture;
  const p = f.prediction;

  return (
    <Link
      href={`/partido/${f.id}`}
      className="ios-list-row-hover"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "12px 14px",
        position: "relative",
        borderTop: showHairline ? "1px solid var(--separator)" : "none",
      }}
    >
      {/* Time */}
      <div style={{ width: 50, flexShrink: 0 }}>
        <MatchClock startingAt={f.starting_at} status={f.state} compact />
      </div>

      {/* Teams */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <TeamCrest
          name={f.home_team_name}
          shortCode={f.home_team_short}
          logoUrl={f.home_team_logo}
          primaryColor={f.home_team_primary_color}
          secondaryColor={f.home_team_secondary_color}
          size="sm"
        />
        <span
          style={{
            color: "var(--label-primary)",
            fontWeight: 500,
            fontSize: "0.875rem",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
        >
          {f.home_team_name}
        </span>
      </div>

      <span
        style={{
          color: "var(--tint-blue)",
          fontSize: "0.7rem",
          fontWeight: 700,
          margin: "0 4px",
        }}
      >
        vs
      </span>

      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          gap: 8,
          justifyContent: "flex-end",
        }}
      >
        <span
          style={{
            color: "var(--label-primary)",
            fontWeight: 500,
            fontSize: "0.875rem",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
            textAlign: "right",
          }}
        >
          {f.away_team_name}
        </span>
        <TeamCrest
          name={f.away_team_name}
          shortCode={f.away_team_short}
          logoUrl={f.away_team_logo}
          primaryColor={f.away_team_primary_color}
          secondaryColor={f.away_team_secondary_color}
          size="sm"
        />
      </div>

      {/* Pick badge */}
      {p?.predicted_outcome && (
        <div style={{ flexShrink: 0 }}>
          <PickBadge outcome={p.predicted_outcome} size="sm" />
        </div>
      )}
    </Link>
  );
}

// ─── Empty state ────────────────────────────────────────────────────────
function EmptyState({ month, year }: { month: string; year: number }) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "40px 20px",
        background: "var(--bg-elevated)",
        border: "1px solid var(--hairline)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <p
        style={{
          fontSize: "1rem",
          fontWeight: 700,
          color: "var(--label-primary)",
        }}
      >
        Sin partidos en {month} {year}
      </p>
      <p
        style={{
          fontSize: "0.875rem",
          color: "var(--label-tertiary)",
          marginTop: 6,
        }}
      >
        Usa las flechas para navegar a otro mes
      </p>
    </div>
  );
}