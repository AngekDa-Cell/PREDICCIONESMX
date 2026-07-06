"use client";
// PageHeader — consistent header for every page
// Usage: <PageHeader title="Partidos" subtitle="..." backHref="/">...</PageHeader>

import Link from "next/link";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  backHref?: string;
  trailing?: React.ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  subtitle,
  backHref,
  trailing,
  className = "",
}: PageHeaderProps) {
  return (
    <header
      className={`px-4 pt-4 pb-3 ios-hairline-b ${className}`}
      style={{ background: "var(--bg-base)" }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {backHref && (
            <Link
              href={backHref}
              className="inline-flex items-center gap-1 text-[12px] mb-2 transition-colors"
              style={{ color: "var(--tint-blue)" }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <path
                  d="M8 1L3 6L8 11"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Volver
            </Link>
          )}
          <h1
            className="ios-title-2 font-bold"
            style={{ color: "var(--label-primary)" }}
          >
            {title}
          </h1>
          {subtitle && (
            <p
              className="ios-subhead mt-0.5"
              style={{ color: "var(--label-secondary)" }}
            >
              {subtitle}
            </p>
          )}
        </div>
        {trailing && <div className="shrink-0">{trailing}</div>}
      </div>
    </header>
  );
}
