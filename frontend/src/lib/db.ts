// src/lib/db.ts
import 'server-only'
import postgres from 'postgres'

if (!process.env.ATLAS_DB_URL) {
  throw new Error('ATLAS_DB_URL is not defined. Set it in .env.local.')
}

const isPooler = process.env.ATLAS_DB_URL.includes('pooler.supabase.com')

// M13: sql.begin() + SET LOCAL requires session-mode pooler (port 5432).
// Transaction-mode pooler (port 6543) releases the connection between
// statements — SET LOCAL has no effect and audit rows get NULL change_reason,
// which is a SEBI compliance gap. Fail fast at module load.
if (process.env.ATLAS_DB_URL.includes(':6543/')) {
  throw new Error(
    'ATLAS_DB_URL must use session-mode pooler (port 5432), not transaction-mode (port 6543). ' +
    'M13 audit trail relies on sql.begin() + SET LOCAL which requires a pinned connection.',
  )
}

const sql = postgres(process.env.ATLAS_DB_URL, {
  max: 5,
  idle_timeout: 20,
  connect_timeout: 10,
  // Transaction-mode pooler (Supabase) doesn't support prepared statements
  prepare: !isPooler,
  ssl: process.env.ATLAS_DB_URL.includes('sslmode=require')
    ? { rejectUnauthorized: false }
    : false,
})

export default sql
