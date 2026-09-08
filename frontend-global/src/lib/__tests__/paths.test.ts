// The session gate's path rules: /health (operator surface), /login (form + callback) and
// /api/revalidate (the bearer-guarded publish webhook) are the only routes reachable without a
// session; a post-login destination is never an external URL.
import { describe, expect, it } from 'vitest'
import { isPublicPath, magicLinkRedirect, postLoginPath, safeNext } from '@/lib/supabase/paths'

describe('isPublicPath', () => {
  it('keeps the operator surface, the sign-in flow and the publish webhook open', () => {
    expect(isPublicPath('/health')).toBe(true)
    expect(isPublicPath('/login')).toBe(true)
    expect(isPublicPath('/login/callback')).toBe(true)
    expect(isPublicPath('/api/revalidate')).toBe(true) // bearer-guarded by the route itself
  })

  it('gates everything else', () => {
    expect(isPublicPath('/')).toBe(false)
    expect(isPublicPath('/etfs')).toBe(false)
    expect(isPublicPath('/healthcheck')).toBe(false)
    expect(isPublicPath('/admin/thresholds')).toBe(false)
    expect(isPublicPath('/api')).toBe(false)
    expect(isPublicPath('/api/revalidated')).toBe(false)
  })
})

describe('safeNext', () => {
  it('follows a same-origin path', () => {
    expect(safeNext('/etfs/SPY')).toBe('/etfs/SPY')
  })

  it('refuses anything that could leave the origin', () => {
    expect(safeNext('https://example.com')).toBe('/')
    expect(safeNext('//example.com')).toBe('/')
    expect(safeNext('/\\example.com')).toBe('/')
    expect(safeNext(null)).toBe('/')
    expect(safeNext(undefined)).toBe('/')
  })
})

// Served under a sub-path (ATLAS_GLOBAL_BASE_PATH=/global on the box), these two URLs are the
// only ones the app builds from an origin rather than letting Next route them — so they are the
// only two that can silently land a reader on the India board, which serves /etfs and /stocks
// under the same domain. A dropped prefix is not a 404 there; it is the wrong market's page.
describe('sub-path URLs the sign-in flow builds itself', () => {
  it('points the magic link at this board’s callback under the prefix', () => {
    expect(magicLinkRedirect('https://atlas.jslwealth.in', '/global', '/etfs/SPY')).toBe(
      'https://atlas.jslwealth.in/global/login/callback?next=%2Fetfs%2FSPY',
    )
  })

  it('sends the reader back under the prefix after the exchange', () => {
    expect(postLoginPath('/global', '/etfs/SPY')).toBe('/global/etfs/SPY')
    expect(postLoginPath('/global', '/')).toBe('/global') // not '/global/': that is a 308
    expect(postLoginPath('/global', '/login?error=link')).toBe('/global/login?error=link')
  })

  it('is unchanged at the root, where the prefix is empty', () => {
    expect(magicLinkRedirect('http://localhost:3000', '', '/')).toBe(
      'http://localhost:3000/login/callback?next=%2F',
    )
    expect(postLoginPath('', '/etfs')).toBe('/etfs')
    expect(postLoginPath('', '/')).toBe('/')
  })
})
