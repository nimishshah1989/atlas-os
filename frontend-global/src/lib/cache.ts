// src/lib/cache.ts — every board query that shows nightly data is cached under the one tag the
// orchestrator flushes (`eod`, src/lib/revalidate.ts) once the gates have passed. A query that is
// not wrapped here does not refresh on publish; a page whose queries all are, does.
//
// unstable_cache stores JSON: wrapped functions must take and return plain values (strings,
// numbers, booleans, null, arrays, objects) — dates and NUMERICs are selected as text.
import { unstable_cache } from 'next/cache'
import { TAG } from '@/lib/revalidate'

export function eodCached<A extends unknown[], R>(fn: (...args: A) => Promise<R>, key: string): (...args: A) => Promise<R> {
  return unstable_cache(fn, [key], { tags: [TAG] })
}
