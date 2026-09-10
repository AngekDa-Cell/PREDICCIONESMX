import type { Metadata, Viewport } from "next";
import "./globals.css";
import { TopNav } from "@/components/layout/Navigation";

export const metadata: Metadata = {
  title: "Quinielas MX — Predicciones Liga MX",
  description:
    "Predicciones de la Liga MX con ensemble numérico (xG + Elo + Dixon-Coles) y heurísticas calibradas.",
  icons: {
    icon: [
      {
        url: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%234781ff'/><text x='50%' y='54%' dominant-baseline='middle' text-anchor='middle' font-size='16' font-weight='900' fill='white'>⚽</text></svg>",
        type: "image/svg+xml",
      },
    ],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#040612",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800;900&display=swap"
        />
      </head>
      <body>
        <TopNav />
        <main className="cp-container py-4 pb-28 md:pl-60 md:pb-8 md:pr-6">{children}</main>
        <footer
          className="py-6 text-center border-t ios-hairline-t"
          style={{ borderColor: "var(--separator)" }}
        >
          <p className="ios-caption" style={{ color: "var(--label-tertiary)" }}>
            Quinielas MX · Solo Liga MX · Datos via SportMonks API v3
          </p>
        </footer>
      </body>
    </html>
  );
}
