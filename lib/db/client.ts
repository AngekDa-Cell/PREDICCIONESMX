// Singleton better-sqlite3 client para Next.js
//
// Usamos better-sqlite3 en lugar de Prisma porque:
// - No requiere libssl 1.1 (Prisma binary falla en Alpine Linux)
// - Read-only directo (más rápido)
// - SQL nativo (más control)
//
// Patrón singleton para evitar reconexiones en dev mode con HMR.
//
// [PREDICCIONESMX 2026-09-10] Lazy init: no abrimos la BD al importar el módulo.
// Esto permite que `next build` corra sin BD accesible (build-time), y que
// cualquier fallo de apertura se propague al primer uso real, no al import.

import Database from "better-sqlite3";

const DB_PATH =
  process.env.DATABASE_PATH ||
  "/workspace/proyectos/data/predictions_mx.db";

const globalForDb = global as unknown as {
  db: Database.Database | undefined;
};

function createDb(): Database.Database {
  // BD principal en RO (montada desde el host con :ro).
  // No se aplican pragma de escritura (romperían next build al no poder
  // cambiar journal_mode). Solo el cliente de votos (RW) necesita autocheckpoint.
  return new Database(DB_PATH, { readonly: true, fileMustExist: true });
}

function getDb(): Database.Database {
  if (!globalForDb.db) {
    globalForDb.db = createDb();
  }
  return globalForDb.db;
}

// Proxy que delega TODO al singleton lazy. Permite usar `db.prepare(...)` etc.
// sin abrir la BD hasta el primer uso.
export const db: Database.Database = new Proxy({} as Database.Database, {
  get(_target, prop, _receiver) {
    const real = getDb();
    const value = (real as any)[prop];
    return typeof value === "function" ? value.bind(real) : value;
  },
});
