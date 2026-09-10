"use client";
// Navigation — NO top bar (per user request 2026-07-02).
// - Mobile: bottom tab bar (iPhone HIG)
// - Desktop: left sidebar (iPad landscape / macOS HIG)
// Branding moves to footer + sidebar header.
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Vote,
  Trophy,
  Users,
  BarChart3,
  type LucideIcon,
} from "lucide-react";

interface NavItem {
  href: string;
  label: string;
  Icon: LucideIcon;
}

const NAV_ITEMS: ReadonlyArray<NavItem> = [
  { href: "/", label: "Inicio", Icon: Home },
  { href: "/votacion", label: "Votación", Icon: Vote },
  { href: "/calendario", label: "Calendario", Icon: Trophy },
  { href: "/equipos", label: "Equipos", Icon: Users },
  { href: "/resultados", label: "Resultados", Icon: BarChart3 },
];

function isActive(href: string, pathname: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function TopNav() {
  const pathname = usePathname();

  return (
    <>
      {/* ─── Desktop sidebar (left) ─── */}
      <aside
        className="hidden md:flex flex-col fixed left-0 top-0 bottom-0 w-60 z-40"
        style={{
          background: "rgba(0, 0, 0, 0.6)",
          backdropFilter: "saturate(180%) blur(20px)",
          WebkitBackdropFilter: "saturate(180%) blur(20px)",
          borderRight: "0.5px solid var(--hairline)",
        }}
        aria-label="Navegación principal"
      >
        {/* Brand */}
        <Link
          href="/"
          className="flex items-center gap-2.5 px-4 h-14 transition-opacity hover:opacity-80 shrink-0"
          aria-label="Quinielas MX — Inicio"
        >
          <span
            className="flex items-center justify-center w-9 h-9 rounded-[10px] font-black text-[16px]"
            style={{
              background: "var(--gradient-cta)",
              color: "#FFFFFF",
              boxShadow: "0 4px 12px rgba(71,129,255,0.35)",
            }}
          >
            ⚽
          </span>
          <span
            style={{
              fontSize: "1rem",
              fontWeight: 700,
              letterSpacing: "-0.01em",
              color: "var(--label-primary)",
            }}
          >
            Quinielas MX
          </span>
        </Link>

        {/* Nav items */}
        <nav className="flex-1 px-2 py-2 space-y-0.5">
          {NAV_ITEMS.map(({ href, label, Icon }) => {
            const active = isActive(href, pathname);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`cp-nav-link flex items-center gap-3 px-3 h-9 rounded-lg text-[14px] transition-all active:scale-[0.98] ${active ? "active" : ""}`}
                style={{
                  color: active ? "var(--tint-blue)" : "var(--label-primary)",
                  fontWeight: active ? 700 : 500,
                  background: active ? "var(--tint-blue-bg)" : "transparent",
                }}
              >
                <Icon
                  size={18}
                  strokeWidth={active ? 2.4 : 1.8}
                  aria-hidden="true"
                />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div
          className="px-4 py-3 text-[11px] shrink-0"
          style={{ color: "var(--label-tertiary)" }}
        >
          <p>Solo Liga MX</p>
          <p className="mt-0.5" style={{ color: "var(--label-quaternary)" }}>
            v7 · Cinépolis redesign
          </p>
        </div>
      </aside>

      {/* ─── Mobile bottom tab bar ─── */}
      <nav
        className="md:hidden fixed bottom-0 left-0 right-0 z-50 pb-[env(safe-area-inset-bottom)]"
        style={{
          background: "rgba(0, 0, 0, 0.78)",
          backdropFilter: "saturate(180%) blur(30px)",
          WebkitBackdropFilter: "saturate(180%) blur(30px)",
          borderTop: "0.5px solid var(--hairline)",
        }}
        aria-label="Navegación principal"
      >
        <ul className="flex items-stretch justify-around px-2 pt-1.5 pb-1.5">
          {NAV_ITEMS.map(({ href, label, Icon }) => {
            const active = isActive(href, pathname);
            return (
              <li key={href} className="flex-1 min-w-0">
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className="flex flex-col items-center gap-0.5 py-1.5 transition-opacity active:opacity-60"
                  style={{ color: active ? "var(--tint-blue)" : "var(--label-secondary)" }}
                >
                  <Icon
                    size={24}
                    strokeWidth={active ? 2.4 : 1.8}
                    fill={active ? "currentColor" : "none"}
                    fillOpacity={active ? 0.15 : 0}
                  />
                  <span
                    className="text-[10px] leading-none tracking-tight"
                    style={{ fontWeight: active ? 600 : 500 }}
                  >
                    {label}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
