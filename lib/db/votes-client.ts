// Cliente SQLite ESCRIBIBLE para la BD de votos
//
// Separado de `client.ts` (que es readonly para la BD principal).
// Esta conexión abre la BD de votos en modo read+write.
//
// [PREDICCIONESMX 2026-09-10] Lazy init (igual que client.ts): no abrimos la BD
// al importar el módulo. Esto evita que `next build` y rutas que solo leen la
// BD principal fallen si la BD de votos no está lista o no se usa.

import Database from "better-sqlite3";

const VOTES_DB_PATH =
  process.env.VOTES_DATABASE_PATH ||
  process.env.VOTES_DB_PATH ||
  "/workspace/proyectos/data/votes_mx.db";

const globalForVotesDb = global as unknown as {
  votesDb: Database.Database | undefined;
};

function createVotesDb(): Database.Database {
  // Asegurar que el directorio existe (cuando se ejecuta fuera de Docker)
  const path = require("path") as typeof import("path");
  const dir = path.dirname(VOTES_DB_PATH);
  try {
    require("fs").mkdirSync(dir, { recursive: true });
  } catch {
    // ignore
  }
  const db = new Database(VOTES_DB_PATH);
  db.pragma("journal_mode = WAL");
  db.pragma("synchronous = NORMAL");
  // [A.1] Auto-checkpoint: mergea WAL a DB principal cada ~400 KB.
  // Sin esto, votos quedan atrapados en el WAL y se pierden si el
  // container reinicia o se cae. (Bug crítico detectado en auditoría.)
  db.pragma("wal_autocheckpoint = 100");
  db.pragma("foreign_keys = ON");
  // Migraciones idempotentes
  db.exec(`
    CREATE TABLE IF NOT EXISTS votes (
      fixture_id INTEGER NOT NULL,
      client_hash TEXT NOT NULL,
      pick TEXT NOT NULL CHECK(pick IN ('home','draw','away')),
      ip_prefix TEXT,
      ua_fingerprint TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (fixture_id, client_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_votes_fixture ON votes(fixture_id);
    CREATE INDEX IF NOT EXISTS idx_votes_created ON votes(created_at);

    CREATE TABLE IF NOT EXISTS vote_meta (
      fixture_id INTEGER PRIMARY KEY,
      first_vote_at TEXT,
      last_vote_at TEXT,
      vote_count INTEGER DEFAULT 0
    );
  `);
  return db;
}

function getVotesDb(): Database.Database {
  if (!globalForVotesDb.votesDb) {
    globalForVotesDb.votesDb = createVotesDb();
  }
  return globalForVotesDb.votesDb;
}

// Proxy lazy — no abre la BD hasta el primer uso real.
export const votesDb: Database.Database = new Proxy(
  {} as Database.Database,
  {
    get(_target, prop, _receiver) {
      const real = getVotesDb();
      const value = (real as any)[prop];
      return typeof value === "function" ? value.bind(real) : value;
    },
  }
);
