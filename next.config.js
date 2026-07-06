/** @type {import('next').NextConfig} */
const securityHeaders = [
  // Prevenir clickjacking
  {
    key: "X-Frame-Options",
    value: "DENY",
  },
  // Prevenir MIME-type sniffing
  {
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  // XSS Protection (legacy + moderno)
  {
    key: "X-XSS-Protection",
    value: "1; mode=block",
  },
  // Referrer policy
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  // Permissions policy
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  // Content Security Policy
  // quinielas.lol es estático (no scripts externos, no inline JS)
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'", // Next.js requiere inline scripts
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com", // Google Fonts (Montserrat)
      "img-src 'self' data: https:",         // logos de equipos
      "font-src 'self' data: https://fonts.gstatic.com",
      "connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
  // HSTS — activo (HTTPS validado en quinielas.lol con Let's Encrypt R10)
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains",
  },
];

const nextConfig = {
  reactStrictMode: true,
  output: "standalone", // Required for Docker — produces minimal server.js
  // [A.6] Ocultar X-Powered-By (filtra stack info).
  poweredByHeader: false,
  // [A.2] Excluir .env* del bundle standalone — la imagen NO debe contener
  // secretos como VOTES_TOKEN_SALT. Las env se pasan via --env-file al run.
  outputFileTracingExcludes: {
    "*": [".env*", "**/.env*", "**/.env.*"],
  },
  // Headers de seguridad en TODAS las rutas
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
  experimental: {
    serverActions: {
      allowedOrigins: ["quinielas.lol", "localhost"],
    },
  },
};

module.exports = nextConfig;