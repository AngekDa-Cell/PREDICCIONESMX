/**
 * EmptyState — Migrado del front viejo (NoMatchesMessage)
 *
 * Patrón signature: border-dashed + rounded-[3rem] + label minúscula
 * uppercase tracking-widest. Da un look profesional en estados vacíos.
 */
export default function EmptyState({
  title,
  subtitle,
  icon = "!",
}: {
  title: string;
  subtitle?: string;
  icon?: string;
}) {
  return (
    <div className="text-center p-16 sm:p-20 border border-dashed border-slate-800 rounded-3xl bg-slate-900/30 animate-fade-in">
      <div className="text-slate-700 text-5xl mb-4 font-black">{icon}</div>
      <p className="text-slate-400 font-black uppercase text-[10px] tracking-[0.2em] mb-1">
        {title}
      </p>
      {subtitle && (
        <p className="text-slate-600 text-xs uppercase tracking-widest mt-2">
          {subtitle}
        </p>
      )}
    </div>
  );
}