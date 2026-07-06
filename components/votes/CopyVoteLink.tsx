"use client";

// CopyVoteLink — muestra la URL compartible y permite copiarla

import { useState, useEffect } from "react";

interface Props {
  token: string;
}

export function CopyVoteLink({ token }: Props) {
  const [url, setUrl] = useState<string>("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const base = window.location.origin;
      setUrl(`${base}/voto/${token}`);
    }
  }, [token]);

  const handleCopy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const input = document.createElement("input");
      input.value = url;
      document.body.appendChild(input);
      input.select();
      try {
        document.execCommand("copy");
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch { /* ignore */ }
      document.body.removeChild(input);
    }
  };

  return (
    <div
      className="mt-2"
      style={{
        background: "var(--bg-grouped-primary, #000)",
        borderRadius: 10,
        padding: "12px",
        border: "0.5px solid rgba(255,255,255,0.08)",
      }}
    >
      <p
        className="ios-footnote font-semibold mb-2"
        style={{ color: "var(--label-secondary)" }}
      >
        Comparte este link con tus clientes:
      </p>
      <div className="flex items-center gap-2">
        <code
          className="ios-footnote flex-1 truncate"
          style={{
            color: "var(--tint-blue)",
            background: "rgba(10,132,255,0.08)",
            padding: "8px 10px",
            borderRadius: 6,
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {url || `quinielas.lol/voto/${token}`}
        </code>
        <button
          onClick={handleCopy}
          className="ios-footnote font-semibold"
          style={{
            color: "white",
            background: copied ? "#30D158" : "var(--tint-blue)",
            border: 0,
            padding: "8px 14px",
            borderRadius: 6,
            minWidth: 80,
          }}
        >
          {copied ? "✓ Copiado" : "Copiar"}
        </button>
      </div>
    </div>
  );
}
