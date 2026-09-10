"use client";
// BackButton — iOS HIG-compliant back navigation
// - chevron ‹ + label contextual
// - 44pt touch target (Apple minimum)
// - tinted blue per HIG
import Link from "next/link";
import { ChevronLeft } from "lucide-react";

interface BackButtonProps {
  href: string;
  label?: string;
}

export function BackButton({ href, label = "Atrás" }: BackButtonProps) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-0.5 -ml-1.5 px-1.5 py-1.5 rounded-md transition-opacity active:opacity-50"
      style={{ color: "var(--tint-blue)", minHeight: 44, minWidth: 44 }}
      aria-label={`Volver a ${label}`}
    >
      <ChevronLeft size={22} strokeWidth={2.4} aria-hidden="true" />
      <span className="text-[17px] leading-none" style={{ fontWeight: 400 }}>
        {label}
      </span>
    </Link>
  );
}
