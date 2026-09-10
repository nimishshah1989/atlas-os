// src/lib/cache.ts — every board query that shows nightly data is cached here, under one tag and
// one maximum age. A query not wrapped here never refreshes on publish; a page whose queries all
// are, does.
//
// WHY THERE IS A MAX AGE AND NOT ONLY A TAG. The tag was the ONLY way a new score reached a
// reader: the orchestrator POSTs {"tag":"eod"} to /api/revalidate with a shared bearer, and the
// pages re-render. That webhook needs GLOBAL_REVALIDATE_URL and GLOBAL_REVALIDATE_SECRET set on
// the box AND the same secret set on the deployment. On 2026-09-10 neither was ever set, so
// publish had NEVER fired — not once — and `unstable_cache` with a tag and no age caches until
// something invalidates it. The board served the same numbers for a week while the nightly wrote
// fresh ones every night, and the only trace was one line in a log file on the box:
//
//   SKIP publish — GLOBAL_REVALIDATE_URL / GLOBAL_REVALIDATE_SECRET unset (box .env)
//
// A cache flush is not worth a distributed system. Two processes, a shared secret and an HTTP
// round trip, all so a page can notice that a table changed — and every one of those parts can
// fail silently, because a cache that does not flush looks exactly like data that did not change.
//
// So the age is the floor and the webhook is the optimisation. With a max age the board is
// CORRECT BY DEFAULT and at worst EOD_MAX_AGE_SECONDS behind; the webhook, when it is configured,
// only makes it instant. Nothing has to be wired up for a score to reach a reader, which is the
// property that was missing.
//
// Fifteen minutes against a nightly that runs once a day: the staleness nobody notices, and 96
// cold renders a day per page at roughly two seconds each. Not a methodology number (rule #1) —
// no score depends on it; it is how long a cached page may live.
//
// unstable_cache stores JSON: wrapped functions must take and return plain values (strings,
// numbers, booleans, null, arrays, objects) — dates and NUMERICs are selected as text.
import { unstable_cache } from 'next/cache'
import { TAG } from '@/lib/revalidate'

/** How long a cached board page may serve without re-reading Postgres. */
export const EOD_MAX_AGE_SECONDS = 900

export function eodCached<A extends unknown[], R>(fn: (...args: A) => Promise<R>, key: string): (...args: A) => Promise<R> {
  return unstable_cache(fn, [key], { tags: [TAG], revalidate: EOD_MAX_AGE_SECONDS })
}
