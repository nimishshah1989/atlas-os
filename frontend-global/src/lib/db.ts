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

// REFUSES, rather than warns. A warning goes to a pm2 log nobody is reading at the moment it
// matters, and the failure it precedes is not this board's: India's `db.ts` is sized at max 14
// against a hard cap of 15 SESSION-mode slots, so one global process on port 5432 takes the
// last one and the LIVE India board stops answering. The board's own pages degrade to an
// honest "no database" state, which is the right trade against taking down the other market.
//
// This is also the guard against an environment mistake that cannot be seen by reading
// .env.local: the box's .env is `set -a; source`d by the nightly, and @next/env prefers a real
// process env var over the file — so an ATLAS_GLOBAL_DB_URL exported there SILENTLY wins.
if (url && !url.includes(':6543/')) {
  throw new Error(
    '[atlas-global] ATLAS_GLOBAL_DB_URL must be the transaction-mode pooler (port 6543), not ' +
      "session mode. India's session pool holds 14 of the cluster's 15 slots; taking the last " +
      'one stops the live India board. Fix the URL in frontend-global/.env.local — and check ' +
      'the box .env, whose exported value would override the file.',
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
