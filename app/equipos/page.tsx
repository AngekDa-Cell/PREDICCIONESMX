/**
 * /equipos — Índice de equipos Liga MX.
 * Grid estilo iOS (circular avatars + nombre).
 */
import Link from "next/link";
import { getAllTeams } from "@/lib/db";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { Badge } from "@/components/ui/ios";

export const dynamic = "force-dynamic";

export default function EquiposPage() {
  const teams = getAllTeams();

  return (
    <div className="space-y-4 animate-ios-up">
      <PageHeader title="Equipos" subtitle={`${teams.length} equipos`} />

      {teams.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-3 ios-stagger">
          {teams.map((team) => (
            <Link
              key={team.id}
              href={`/equipo/${team.id}`}
              className="flex flex-col items-center gap-2 p-4 rounded-[14px] transition-all active:scale-95"
              style={{ background: "var(--bg-elevated)", border: "0.5px solid var(--hairline)" }}
            >
              <TeamCrest
                name={team.name}
                shortCode={team.short_code}
                logoUrl={team.logo_url}
                primaryColor={team.primary_color}
                secondaryColor={team.secondary_color}
                size="lg"
              />
              <p
                className="ios-subhead font-semibold text-center leading-tight"
                style={{ color: "var(--label-primary)" }}
              >
                {team.short_code || team.name.slice(0, 4)}
              </p>
              {team.country && (
                <p className="ios-caption hidden sm:block" style={{ color: "var(--label-tertiary)" }}>
                  {team.country}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function PageHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="ios-hairline-b pb-3 mb-4">
      <h1 className="ios-title-2 font-bold" style={{ color: "var(--label-primary)" }}>
        {title}
      </h1>
      <p className="ios-subhead mt-0.5" style={{ color: "var(--label-secondary)" }}>
        {subtitle}
      </p>
    </header>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-16 rounded-[14px]" style={{ background: "var(--bg-elevated)" }}>
      <p className="ios-headline" style={{ color: "var(--label-secondary)" }}>
        Sin equipos cargados
      </p>
    </div>
  );
}
