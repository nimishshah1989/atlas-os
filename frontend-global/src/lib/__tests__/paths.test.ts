// The session gate's path rules: /health (operator surface) and /login (form + callback) are the
// only routes reachable without a session; a post-login destination is never an external URL.
import { describe, expect, it } from 'vitest'
import { isPublicPath, safeNext } from '@/lib/supabase/paths'

describe('isPublicPath', () => {
  it('keeps the operator surface and the sign-in flow open', () => {
    expect(isPublicPath('/health')).toBe(true)
    expect(isPublicPath('/login')).toBe(true)
    expect(isPublicPath('/login/callback')).toBe(true)
  })

  it('gates everything else', () => {
    expect(isPublicPath('/')).toBe(false)
    expect(isPublicPath('/etfs')).toBe(false)
    expect(isPublicPath('/healthcheck')).toBe(false)
    expect(isPublicPath('/admin/thresholds')).toBe(false)
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
