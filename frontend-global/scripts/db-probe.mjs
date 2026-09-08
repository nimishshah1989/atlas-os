// scripts/db-probe.mjs — why does /health hang?
//
//     cd frontend-global && node scripts/db-probe.mjs
//
// /health is the ONE route that reaches the database on an unauthenticated request: /login
// answers 200 without a query, and every other route is redirected by the middleware before a
// query runs. So "/health times out while everything else answers" narrows to the database
// path and says nothing about which part of it — connect, TLS, or a slow statement.
//
// This walks that path in four steps with a clock on each, using the SAME options as
// src/lib/db.ts, and prints where the time goes. It is a diagnostic, not a fix: nothing here
// is imported by the board, and it writes nothing.
//
// Read the output like this:
//   step 1 slow or failing  → the pooler is unreachable or refusing (host, port, TLS, password)
//   step 2 slow             → connect succeeds but the pooler is not handing out a backend
//   step 4 slow             → the connection is fine and ONE query is the problem; its name
//                             is printed, and that query is what to fix
//   all four fast           → the hang is not in the database layer at all; look at the
//                             render path, and say so rather than guessing again
import { readFileSync } from 'node:fs'
import { performance } from 'node:perf_hooks'
import postgres from 'postgres'

// .env.local, read the way @next/env does — except that a real environment variable wins,
// which is the trap the box already sprang once: the nightly `set -a; source`s .env, so an
// ATLAS_GLOBAL_DB_URL exported there overrides the file silently. Both are printed.
function fromEnvFile(path) {
  try {
    for (const line of readFileSync(path, 'utf8').split('\n')) {
      const m = /^\s*(?:export\s+)?ATLAS_GLOBAL_DB_URL\s*=\s*(.*)$/.exec(line)
      if (m) return m[1].trim().replace(/^["']|["']$/g, '')
    }
  } catch {
    return null
  }
  return null
}

// The password is never printed — the repo is public and this output gets pasted into chat.
function redact(url) {
  return url.replace(/:\/\/([^:]+):[^@]*@/, '://$1:***@')
}

// Every step races a clock. Without this the probe hangs on exactly the failure it exists to
// find, printing nothing — which is the /health symptom reproduced rather than diagnosed. The
// losing query keeps running on the server; this is a throwaway process, so that is fine.
const STEP_TIMEOUT_S = 15
const TIMED_OUT = Symbol('timed out')

function afterTimeout(seconds) {
  return new Promise((resolve) => setTimeout(() => resolve(TIMED_OUT), seconds * 1000).unref())
}

async function timed(label, fn) {
  const t0 = performance.now()
  try {
    const value = await Promise.race([fn(), afterTimeout(STEP_TIMEOUT_S)])
    const took = ((performance.now() - t0) / 1000).toFixed(1)
    if (value === TIMED_OUT) {
      console.log(`  HUNG ${took}s  ${label}  ← still running after ${STEP_TIMEOUT_S}s`)
      return null
    }
    console.log(`  ok   ${took}s  ${label}`)
    return value
  } catch (err) {
    console.log(`  FAIL ${((performance.now() - t0) / 1000).toFixed(1)}s  ${label}`)
    console.log(`       ${err.message}`)
    return null
  }
}

const fileUrl = fromEnvFile('.env.local')
const envUrl = process.env.ATLAS_GLOBAL_DB_URL
const url = envUrl || fileUrl
if (!url) {
  console.log('no ATLAS_GLOBAL_DB_URL in the environment or .env.local — nothing to probe')
  process.exit(1)
}
console.log(`url        ${redact(url)}`)
console.log(`from       ${envUrl ? 'PROCESS ENV (overrides .env.local)' : '.env.local'}`)
if (envUrl && fileUrl && envUrl !== fileUrl) {
  console.log(`  .env.local holds a DIFFERENT url: ${redact(fileUrl)}`)
  console.log('  the process env is what the board uses — that difference may be the whole bug')
}
console.log(`transaction pooler (:6543)?  ${url.includes(':6543/') ? 'yes' : 'NO — db.ts refuses this'}`)
console.log(`sslmode=require in the url?  ${url.includes('sslmode=require') ? 'yes' : 'no — db.ts then sets ssl:false, i.e. plaintext'}`)

// Exactly src/lib/db.ts's options. A probe that connects differently proves nothing about
// the board, so this must stay in step with that file.
const sql = postgres(url, {
  max: 5,
  prepare: false,
  idle_timeout: 20,
  max_lifetime: 60 * 5,
  connect_timeout: 10,
  ssl: url.includes('sslmode=require') ? { rejectUnauthorized: false } : false,
})

// The four tables /health reads, as THUNKS. A postgres.js tagged template is queued on the
// connection the moment it is constructed, so an array of built queries would fire all four at
// once and every timing below would measure the same wall clock. They are all small ops
// tables — hundreds of rows, no technical_daily, no ohlcv_daily — which is itself a finding:
// if the connection is healthy these cannot take seconds, so a hang here is not a slow query.
const HEALTH_READS = [
  ['atlas_pipeline_runs', () => sql`SELECT count(*)::int AS n FROM atlas_global.atlas_pipeline_runs`],
  ['atlas_validator_results', () => sql`SELECT count(*)::int AS n FROM atlas_global.atlas_validator_results`],
  ['atlas_health_daily', () => sql`SELECT count(*)::int AS n FROM atlas_global.atlas_health_daily`],
  ['provider_calls', () => sql`SELECT count(*)::int AS n FROM atlas_global.provider_calls`],
]

console.log('\nprobing')
await timed('1. connect + SELECT 1', () => sql`SELECT 1 AS ok`)
await timed('2. server identity', async () => {
  const [row] = await sql`SELECT current_user AS who, inet_server_port() AS port`
  console.log(`       role=${row.who} port=${row.port}`)
  return row
})
await timed('3. schema is visible', async () => {
  const [row] = await sql`
    SELECT count(*)::int AS n FROM information_schema.tables WHERE table_schema = 'atlas_global'`
  console.log(`       ${row.n} table(s) in atlas_global`)
  return row
})
for (const [label, run] of HEALTH_READS) {
  const rows = await timed(`4. read ${label}`, run)
  if (rows) console.log(`       ${rows[0].n} row(s)`)
}
await timed('5. the country grid /countries reads', async () => {
  const [row] = await sql`SELECT count(*)::int AS n FROM atlas_global.country_daily`
  console.log(`       ${row.n} country_daily row(s) — 0 means build_country_views.py has not run`)
  return row
})

console.log('\nread the FIRST line above that is not `ok` — everything after it is a consequence')
// A hung query holds its connection, so a graceful end would wait on it. The clock above has
// already reported what there is to report.
await Promise.race([sql.end({ timeout: 5 }), afterTimeout(5)])
process.exit(0)
