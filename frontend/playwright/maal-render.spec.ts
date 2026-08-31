// frontend/playwright/maal-render.spec.ts
// The MaaL pages must still render after the sign-in gate came out. MaalEditor,
// BookCard and MaxCapField all lost a canEdit prop; a stale reference surfaces as
// a 500 at render time, which tsc cannot see. Fetches HTML rather than driving a
// browser — no chromium needed, and a crash is what we are actually looking for.
import { test, expect } from '@playwright/test'

const PAGES = ['/portfolios/maal', '/portfolios/maal/leaders/2026-08-31'] as const

for (const path of PAGES) {
  test(`${path} renders without the gate`, async ({ request }) => {
    const res = await request.get(path, { maxRedirects: 0 })
    expect(res.status()).toBe(200)
    const html = await res.text()
    expect(html).not.toContain('/login')
    expect(html).not.toContain('Sign in')
    expect(html).not.toContain('needs a sign-in')
  })
}
