"use client";

// VoteCopyTokenButton — botón secundario que copia el link público
// de un partido al portapapeles. Muestra "✓ Copiado" 2 segundos.

import { useState } from "react";

interface Props {
  token: string;
  homeTeam: string;
  awayTeam: string;
  className?: string;
}

export function VoteCopyTokenButton({
  token,
  homeTeam,
  awayTeam,
  className,
}: Props) {
  const [copied, setCopied] = useState(false);
  const [errored, setErrored] = useState(false);

  const handleCopy = async () => {
    const url = `${window.location.origin}/voto/${token}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setErrored(false);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Clipboard failed, falling back to prompt", err);
      // Fallback: prompt
      try {
        window.prompt(
          `Copiá este link para ${homeTeam} vs ${awayTeam}:`,
          url,
        );
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        setErrored(true);
        setTimeout(() => setErrored(false), 2000);
      }
    }
  };

  const label = copied ? "✓ Copiado" : errored ? "✗ Error" : "🔗 Compartir";

  return (
    <button
      onClick={handleCopy}
      className={className}
      type="button"
      aria-label={`Copiar link para compartir ${homeTeam} vs ${awayTeam}`}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        padding: "12px 16px",
        background: "var(--bg-elevated-2)",
        border: `1px solid ${
          copied ? "var(--tint-green)" : "var(--separator)"
        }`,
        borderRadius: "var(--radius-md)",
        color: copied
          ? "var(--tint-green)"
          : errored
          ? "var(--tint-red)"
          : "var(--tint-blue)",
        fontWeight: 700,
        fontSize: "0.8rem",
        cursor: "pointer",
        transition: "all var(--dur-fast) var(--ease-ios)",
        minWidth: 100,
      }}
    >
      {label}
    </button>
  );
}