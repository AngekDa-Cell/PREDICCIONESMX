/**
 * HeroSection — Migrado del front viejo (HeroSection Quiniela Express).
 *
 * Rescatado:
 * - Headline gigante con palabra en azul + itálica
 * - 3 cards numeradas con borde hover coloreado (azul/verde/púrpura)
 * - Sección "Cómo funciona" con 4 steps numerados // 01 // 02
 * - CTA blanco→azul en hover (btn-primary)
 *
 * Adaptación a Liga MX:
 * - Titular "LA LIGA MX ESTÁ EN DATOS"
 * - 3 propuestas: Multi-agente · SportMonks data · Debate Bull vs Bear
 * - 4 steps: Ingesta → Features → Debate IA → Resultado
 */

import Link from "next/link";

export default function HeroSection({
  upcomingCount,
  finishedCount,
}: {
  upcomingCount: number;
  finishedCount: number;
}) {
  return (
    <div className="py-12 sm:py-16 animate-fade-in-up">
      {/* HERO */}
      <div className="text-center space-y-8 mb-20">
        <h1 className="text-4xl sm:text-5xl md:text-7xl font-black text-white tracking-tighter leading-none">
          LA LIGA MX ESTÁ <span className="text-blue-500 italic">EN DATOS</span>
          <br />
          Y EN DEBATE.
        </h1>

        <p className="text-slate-400 text-base sm:text-lg md:text-xl max-w-2xl mx-auto leading-relaxed font-medium">
          5 agentes (Bull-Local, Bear-Visita, Contextual, Data Auditor, Juez) analizan cada
          partido con datos de SportMonks y un modelo probabilístico (xG + Elo + Dixon-Coles).
        </p>

        {/* Cards de propuesta de valor */}
        <div className="grid md:grid-cols-3 gap-6 pt-8">
          <ValueCard
            num="01."
            title="Data Real"
            color="blue"
            desc="Información actualizada de la Liga MX via SportMonks API v3."
          />
          <ValueCard
            num="02."
            title="Ensemble"
            color="emerald"
            desc="5 modelos (xG + Elo + Dixon-Coles + heurísticas) ponderan el pick."
          />
          <ValueCard
            num="03."
            title="Bull vs Bear"
            color="purple"
            desc="Debate estructurado para detectar valor oculto en cada partido."
          />
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-8">
          <Link href="/calendario" className="btn-primary">
            Ver {upcomingCount} partidos próximos
          </Link>
          <Link href="#proceso" className="btn-secondary">
            Cómo funciona
          </Link>
        </div>

        {/* Stats inline */}
        <div className="grid grid-cols-3 gap-4 max-w-2xl mx-auto pt-12 border-t border-slate-900">
          <Stat label="Próximos" value={upcomingCount} />
          <Stat label="Finalizados" value={finishedCount} />
          <Stat label="Agentes" value="5" />
        </div>
      </div>

      {/* PROCESO */}
      <div id="proceso" className="mt-16 pt-12 border-t border-slate-900 scroll-mt-24">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-12 gap-4">
          <div>
            <h2 className="text-2xl sm:text-3xl font-black text-white uppercase tracking-tighter">
              Nuestro Proceso
            </h2>
            <p className="text-slate-500 text-sm mt-1">
              Del dato crudo a la predicción final.
            </p>
          </div>
          <div className="hidden md:block h-px flex-1 bg-slate-900 mx-8 mb-3" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 sm:gap-8">
          {[
            {
              step: "01",
              title: "Ingesta",
              desc: "Captura de fixtures, alineaciones y stats de SportMonks.",
            },
            {
              step: "02",
              title: "Features",
              desc: "Forma, H2H, venue, referee, clima y momentum.",
            },
            {
              step: "03",
              title: "Debate",
              desc: "5 agentes argumentan pick por partido.",
            },
            {
              step: "04",
              title: "Juez",
              desc: "DWC-MAD weighting → veredicto final con confianza.",
            },
          ].map((item) => (
            <div key={item.step} className="space-y-3">
              <div className="step-num">// {item.step}</div>
              <h4 className="text-white font-bold text-xs uppercase tracking-wider">
                {item.title}
              </h4>
              <p className="text-slate-500 text-[11px] leading-relaxed italic">
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ValueCard({
  num,
  title,
  desc,
  color,
}: {
  num: string;
  title: string;
  desc: string;
  color: "blue" | "emerald" | "purple";
}) {
  const borderHover = {
    blue: "hover:border-blue-500/50",
    emerald: "hover:border-emerald-500/50",
    purple: "hover:border-purple-500/50",
  }[color];

  const textColor = {
    blue: "text-blue-500",
    emerald: "text-emerald-500",
    purple: "text-purple-500",
  }[color];

  return (
    <div
      className={`bg-slate-900/50 p-6 sm:p-8 rounded-3xl border border-slate-800 ${borderHover} transition-all group text-left`}
    >
      <div
        className={`${textColor} text-2xl mb-2 font-black group-hover:scale-110 transition-transform inline-block`}
      >
        {num}
      </div>
      <h3 className="text-white font-bold mb-2 text-sm uppercase tracking-wider">
        {title}
      </h3>
      <p className="text-slate-500 text-xs leading-relaxed">{desc}</p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="text-center">
      <div className="text-2xl sm:text-3xl font-black text-white">{value}</div>
      <div className="label-mini mt-1">{label}</div>
    </div>
  );
}