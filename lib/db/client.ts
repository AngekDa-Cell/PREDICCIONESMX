// Singleton better-sqlite3 client para Next.js
//
// Usamos better-sqlite3 en lugar de Prisma porque:
// - No requiere libssl 1.1 (Prisma binary falla en Alpine Linux)
// - Read-only directo (más rápido)
// - SQL nativo (más control)
//
// Patrón singleton para evitar reconexiones en dev mode con HMR.

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

export const db: Database.Database = globalForDb.db ?? createDb();

if (process.env.NODE_ENV !== "production") {
  globalForDb.db = db;
}
