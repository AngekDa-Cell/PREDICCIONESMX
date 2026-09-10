"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Link de navegación con estado activo visual.
 * Migrado del patrón del front viejo (text-blue-500 cuando currentView === id).
 *
 * En el server layout no se puede usar usePathname(), por eso este
 * componente es client y se monta dentro del header sticky.
 */
export default function ActiveNavLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isActive = pathname === href || (href !== "/" && pathname?.startsWith(href));

  return (
    <Link
      href={href}
      className={`text-xs font-black uppercase tracking-widest transition-colors ${
        isActive ? "text-blue-500" : "text-slate-400 hover:text-white"
      }`}
    >
      {children}
    </Link>
  );
}