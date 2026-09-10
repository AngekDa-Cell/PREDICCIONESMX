// app/api/health/route.ts — Healthcheck HTTP para Traefik / Dokploy / monitoring
// Responde 200 con info del servicio. Acceso a BD best-effort.

import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  const uptime = Math.floor(process.uptime());
  let dbOk = false;
  try {
    const { db } = await import('@/lib/db/client');
    db.prepare('SELECT 1').get();
    dbOk = true;
  } catch (e) {
    dbOk = false;
  }
  return NextResponse.json({
    status: 'ok',
    service: 'predicciones-mx-front',
    uptime_seconds: uptime,
    db: dbOk ? 'ok' : 'unavailable',
  });
}

