import { describe, expect, it } from 'vitest'
import { cookieScope } from '../cookieScope'

describe('cookieScope', () => {
  it('is the base path when the board is served under one', () => {
    expect(cookieScope('/global')).toBe('/global')
  })

  it('is "/" at the root, never the empty string', () => {
    // Path="" is not a valid cookie attribute: the browser falls back to the request URI's
    // directory, so a cookie set on /login/callback would not be sent on /etfs.
    expect(cookieScope('')).toBe('/')
  })

  it('never keeps a trailing slash', () => {
    // "/global/" + "/etfs" is a 404, and a Path with a trailing slash does not match "/global".
    expect(cookieScope('/global/')).toBe('/global')
    expect(cookieScope('/')).toBe('/')
  })
})
