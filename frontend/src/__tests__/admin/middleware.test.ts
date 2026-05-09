// Regression test: /admin/* lives under the existing site-wide auth gate.
//
// M13 explicitly chose to NOT add a separate admin token. Single user (Bhaven,
// the FM), single password. The matcher in frontend/middleware.ts already
// catches everything except _next/static, _next/image, favicon.ico, robots.txt
// — including /admin/thresholds. This file documents and locks that contract.
//
// If a future change splits the admin gate (HMAC token, role-based), update
// these tests to cover the new branch logic.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

import { middleware } from '../../../middleware'

const ORIGIN = 'http://localhost:3000'
const SITE_PASSWORD = 'site-test-pw'

function makeRequest(path: string, cookieValue?: string): NextRequest {
  const req = new NextRequest(`${ORIGIN}${path}`)
  if (cookieValue !== undefined) {
    req.cookies.set('atlas_auth', cookieValue)
  }
  return req
}

describe('middleware /admin gate', () => {
  beforeEach(() => {
    vi.stubEnv('ATLAS_PASSWORD', SITE_PASSWORD)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('redirects /admin/thresholds to /login when no atlas_auth cookie', () => {
    const res = middleware(makeRequest('/admin/thresholds'))

    expect(res.status).toBe(307)
    const location = res.headers.get('location')
    expect(location).toContain('/login')
    // Round-trip target preserved so the user lands back on /admin/thresholds
    // after a successful login.
    expect(location).toContain('from=%2Fadmin%2Fthresholds')
  })

  it('redirects /admin/thresholds to /login when cookie value is wrong', () => {
    const res = middleware(makeRequest('/admin/thresholds', 'wrong-password'))

    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('passes /admin/thresholds through when atlas_auth matches ATLAS_PASSWORD', () => {
    const res = middleware(makeRequest('/admin/thresholds', SITE_PASSWORD))

    // NextResponse.next() returns 200 with no Location header
    expect(res.status).toBe(200)
    expect(res.headers.get('location')).toBeNull()
  })

  it('does not gate /login itself (would create a redirect loop)', () => {
    const res = middleware(makeRequest('/login'))

    expect(res.status).toBe(200)
    expect(res.headers.get('location')).toBeNull()
  })

  it('redirects nested /admin paths the same way (e.g. /admin/foo/bar)', () => {
    const res = middleware(makeRequest('/admin/foo/bar'))

    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
    expect(res.headers.get('location')).toContain('from=%2Fadmin%2Ffoo%2Fbar')
  })
})
