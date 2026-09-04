// src/lib/db.ts — postgres.js against the Supabase TRANSACTION-mode pooler (port 6543).
//
// Ported from frontend/src/lib/db.ts with the opposite pooling contract: in transaction mode a
// connection is released after every statement, so prepared statements are off (prepare: false)
// and nothing may rely on SET LOCAL or other session state — audit rows carry changed_by and
// change_reason as columns instead (docs/global/plan.md § Frontend + hosting + auth).
//
// This module never throws at import time. A deployment without ATLAS_GLOBAL_DB_URL (a Vercel
// preview, a fresh laptop) builds and serves; pages read `dbAvailable` and render an honest
// "no database configured" state.
import 'server-only'
import postgres from 'postgres'

type Db = ReturnType<typeof postgres>

const url = process.env.ATLAS_GLOBAL_DB_URL

/** True when this deployment has a database. Every page checks it before querying. */
export const dbAvailable = Boolean(url)

if (url && !url.includes(':6543/')) {
  console.warn(
    '[atlas-global] ATLAS_GLOBAL_DB_URL is not the transaction-mode pooler (port 6543). ' +
      'The global board is sized for it (max 5 per instance); session mode shares India\'s 15 slots.',
  )
}

// max: 5 per function instance — Vercel scales instances horizontally and the pooler
// multiplexes; idle connections are recycled quickly so cold instances do not pin slots.
const client: Db | null = url
  ? postgres(url, {
      max: 5,
      prepare: false,
      idle_timeout: 20,
      max_lifetime: 60 * 5,
      connect_timeout: 10,
      ssl: url.includes('sslmode=require') ? { rejectUnauthorized: false } : false,
    })
  : null

/** The tagged-template client. Throws a plain sentence when the deployment has no database. */
export function db(): Db {
  if (!client) {
    throw new Error('ATLAS_GLOBAL_DB_URL is not set — this deployment has no database.')
  }
  return client
}
