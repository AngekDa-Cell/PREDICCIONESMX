import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // === LEGACY (preservado por compatibilidad con código existente) ===
        lmx: {
          bg: "#020617",          // slate-950 (más oscuro que el #0a0e1a anterior)
          card: "#0f172a",        // slate-900
          accent: "#3b82f6",      // blue-500 (en lugar de #1e3a8a)
          gold: "#fbbf24",        // amber-400
          green: "#10b981",       // emerald-500
          red: "#ef4444",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Inter",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in-zoom": {
          from: { opacity: "0", transform: "scale(0.95)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.5s ease-out",
        "fade-in-up": "fade-in-up 0.5s ease-out",
        "fade-in-zoom": "fade-in-zoom 0.3s ease-out",
        "fade-in-up-slow": "fade-in-up 0.7s ease-out",
      },
    },
  },
  darkMode: "class",
  plugins: [],
};

export default config;