// frontend/playwright/no-auth.spec.ts
// The board carries no sign-in: every MaaL write route must be reachable without
// an atlas_auth cookie. Each POST sends a deliberately invalid body, so reaching
// the route's own 400 proves the request got past the gate rather than being
// turned away. maxRedirects:0 matters — a redirect to /login must read as a
// failure here, not be quietly followed into a 200.
import { test, expect } from '@playwright/test'

const WRITE_ROUTES = [
  '/api/maal/cap',
  '/api/maal/save',
  '/api/maal/publish',
  '/api/maal/reopen',
  '/api/maal/image',
  '/api/desk/orders',
] as const

for (const route of WRITE_ROUTES) {
  test(`${route} does not demand a sign-in`, async ({ request }) => {
    const res = await request.post(route, {
      headers: { 'Content-Type': 'application/json' },
      data: {},
      maxRedirects: 0,
    })
    expect(res.status()).toBe(400)
    expect((await res.json()).error_code).toBe('bad_request')
  })
}

test('no /login page is served', async ({ request }) => {
  const res = await request.get('/login', { maxRedirects: 0 })
  expect(res.status()).toBe(404)
})
