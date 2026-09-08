// src/lib/revalidate.ts — the publish webhook's two decisions, pure so they are unit-tested without
// a request: is the bearer right (constant-time), is the body {"tag":"eod"}. The route handler
// (src/app/api/revalidate/route.ts) asks them in that order — the body is read only after the bearer
// passed — and calls revalidateTag.
import { createHash, timingSafeEqual } from 'node:crypto'

/** The one cache tag the orchestrator flushes: every page that shows nightly data. */
export const TAG = 'eod'

export type Verdict = { ok: true } | { ok: false; status: 400 | 401; error: string }

const BEARER = /^Bearer\s+(\S+)$/i

/**
 * True when the Authorization header carries exactly the secret. Both sides are hashed to
 * equal-length digests before timingSafeEqual, so neither the secret's length nor a matching prefix
 * shows in the response time.
 */
export function bearerMatches(header: string | null | undefined, secret: string): boolean {
  const m = BEARER.exec(header ?? '')
  if (!m) return false
  const presented = createHash('sha256').update(m[1]).digest()
  const expected = createHash('sha256').update(secret).digest()
  return timingSafeEqual(presented, expected)
}

/** 401 with no secret configured or a wrong bearer; decided before the body is read. */
export function authorizeBearer(header: string | null | undefined, secret: string | undefined): Verdict {
  if (!secret) {
    return { ok: false, status: 401, error: 'GLOBAL_REVALIDATE_SECRET is not configured on this deployment' }
  }
  if (!bearerMatches(header, secret)) return { ok: false, status: 401, error: 'unauthorized' }
  return { ok: true }
}

/** 400 unless the body is JSON carrying exactly the tag. */
export function checkBody(body: string): Verdict {
  let tag: unknown
  try {
    tag = (JSON.parse(body) as { tag?: unknown } | null)?.tag
  } catch {
    return { ok: false, status: 400, error: `body must be JSON: {"tag":"${TAG}"}` }
  }
  if (tag !== TAG) return { ok: false, status: 400, error: `unknown tag; expected "${TAG}"` }
  return { ok: true }
}
