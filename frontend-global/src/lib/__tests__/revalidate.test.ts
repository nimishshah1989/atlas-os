// The publish webhook's decisions: only the exact bearer, then only the exact body, flushes the tag.
// Secrets here are test strings, not anything deployed.
import { describe, expect, it } from 'vitest'
import { authorizeBearer, bearerMatches, checkBody, TAG } from '@/lib/revalidate'

const SECRET = 'test-secret-9f1c2a54'

describe('bearerMatches', () => {
  it('accepts the exact secret, case-insensitive on the scheme only', () => {
    expect(bearerMatches(`Bearer ${SECRET}`, SECRET)).toBe(true)
    expect(bearerMatches(`bearer ${SECRET}`, SECRET)).toBe(true)
  })

  it('refuses a missing header, another scheme, a prefix, a longer string and a different case', () => {
    expect(bearerMatches(null, SECRET)).toBe(false)
    expect(bearerMatches(undefined, SECRET)).toBe(false)
    expect(bearerMatches('', SECRET)).toBe(false)
    expect(bearerMatches(SECRET, SECRET)).toBe(false) // no scheme
    expect(bearerMatches(`Basic ${SECRET}`, SECRET)).toBe(false)
    expect(bearerMatches(`Bearer ${SECRET.slice(0, -1)}`, SECRET)).toBe(false)
    expect(bearerMatches(`Bearer ${SECRET}x`, SECRET)).toBe(false)
    expect(bearerMatches(`Bearer ${SECRET.toUpperCase()}`, SECRET)).toBe(false)
  })
})

describe('authorizeBearer', () => {
  it('passes the exact bearer', () => {
    expect(authorizeBearer(`Bearer ${SECRET}`, SECRET)).toEqual({ ok: true })
  })

  it('is 401 for a wrong or missing bearer', () => {
    expect(authorizeBearer('Bearer nope', SECRET)).toMatchObject({ ok: false, status: 401 })
    expect(authorizeBearer(null, SECRET)).toMatchObject({ ok: false, status: 401 })
  })

  it('is 401 for every caller when no secret is configured', () => {
    expect(authorizeBearer(`Bearer ${SECRET}`, undefined)).toMatchObject({ ok: false, status: 401 })
    expect(authorizeBearer('Bearer ', '')).toMatchObject({ ok: false, status: 401 })
  })

  it('never echoes the secret in an error', () => {
    const verdicts = [authorizeBearer('Bearer nope', SECRET), authorizeBearer(`Bearer ${SECRET}`, undefined)]
    for (const v of verdicts) expect(JSON.stringify(v)).not.toContain(SECRET)
  })
})

describe('checkBody', () => {
  it('accepts {"tag":"eod"} — the literal the orchestrator sends', () => {
    expect(TAG).toBe('eod')
    expect(checkBody('{"tag":"eod"}')).toEqual({ ok: true })
  })

  it('is 400 for a body that is not {"tag":"eod"}', () => {
    for (const body of ['', 'eod', 'null', '{"tag":"all"}', '{"tag":["eod"]}', '{}']) {
      expect(checkBody(body)).toMatchObject({ ok: false, status: 400 })
    }
  })
})
