"use client";
// TeamCrest — circular avatar with team logo (preferred) or initials (fallback).
// Si `logoUrl` está disponible, muestra el escudo del equipo con borde del color primario.
// Si falla la carga o no hay logo, muestra iniciales con colores corporativos.

import { useState } from "react";

interface TeamCrestProps {
  name: string;
  shortCode?: string | null;
  logoUrl?: string | null;
  primaryColor?: string | null;
  secondaryColor?: string | null;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

const sizeMap = {
  sm: "w-8 h-8 text-[10px]",
  md: "w-11 h-11 text-xs",
  lg: "w-14 h-14 text-sm",
  xl: "w-20 h-20 text-base",
};

export function TeamCrest({
  name,
  shortCode,
  logoUrl,
  primaryColor,
  secondaryColor,
  size = "md",
  className = "",
}: TeamCrestProps) {
  const [imgFailed, setImgFailed] = useState(false);
  const bg = primaryColor || "#2C2C2E";
  const fg = secondaryColor || "#fff";
  const initials = shortCode || name.slice(0, 3).toUpperCase();

  // Si tenemos logo URL y no ha fallado, mostrar el escudo
  if (logoUrl && !imgFailed) {
    return (
      <div
        className={`${sizeMap[size]} ${className} relative shrink-0`}
        style={{
          backgroundColor: bg,
          border: `2px solid ${bg}`,
          borderRadius: "50%",
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        aria-label={name}
        title={name}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={logoUrl}
          alt={name}
          loading="lazy"
          onError={() => setImgFailed(true)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      </div>
    );
  }

  // Fallback: iniciales sobre fondo de color
  return (
    <div
      className={`ios-crest ${sizeMap[size]} ${className}`}
      style={{ backgroundColor: bg, color: fg }}
      aria-label={name}
      title={name}
    >
      {initials}
    </div>
  );
}