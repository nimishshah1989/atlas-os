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

// THE POOL IS THE WHOLE BOARD'S, NOT ONE REQUEST'S — and it was sized as if it were not.
//
// `max: 5` came with the reason "per function instance — Vercel scales instances horizontally",
// and on Vercel that is right: many short-lived instances, five connections each, idle ones
// recycled. This board does not run on Vercel. It is ONE long-lived pm2 process on the box, so
// that five is the entire site's budget — every route, every visitor, every concurrent render.
//
// It held while every query was fast, because a connection came back in milliseconds and nobody
// could see the ceiling. On 2026-09-10 the scored set went from 1,751 funds to 5,486 and some
// renders began taking ten seconds or more. Five of those and the pool is empty; everything
// else queues behind them. The symptom was not "the slow pages are slow" — it was that
// /countries, whose query is cheap, sent its full 171 KB of HTML and then hung forever waiting
// for a connection that was never coming. A wedged pool looks exactly like a broken page.
//
// Worse, it does not recover. A client that gives up does not stop the query it started, and
// nothing here bounds one, so an abandoned request keeps its slot until the process restarts.
// statement_timeout is the fix for that: the DATABASE ends a query the board has stopped
// waiting for, so a slot always comes back. Supabase's transaction pooler may not honour a
// startup parameter, so this is a best-effort backstop and NOT the reason the pool is safe —
// the size is.
//
// 20 costs nothing here. This is the TRANSACTION pooler (:6543, enforced above), which
// multiplexes client connections onto far fewer backends and never touches the 15 SESSION
// slots India's board holds — the constraint that made 5 feel prudent applies to a different
// port entirely.
const client: Db | null = url
  ? postgres(url, {
      max: 20,
      prepare: false,
      idle_timeout: 20,
      max_lifetime: 60 * 5,
      connect_timeout: 10,
      connection: { statement_timeout: 30_000 }, // milliseconds — the type is numeric, not '30s'
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
