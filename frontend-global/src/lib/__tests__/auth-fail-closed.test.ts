// The allowlist is the ONLY thing between a valid Supabase session and this board, so a run that
// cannot read it has authorised nobody — it has merely failed to check. These tests pin that
// distinction, because the fail-OPEN version shipped once and read as harmless: `dbAvailable` is
// only `Boolean(url)`, so a pm2 process started without ATLAS_GLOBAL_DB_URL in its environment
// served every page to anyone holding any Supabase account.
//
// Real module, real control flow: only the two edges are stubbed (the Supabase session, which
// needs a browser, and `redirect`, which throws in Next). Nothing about the allowlist is faked.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const SIGNED_IN = 'nimish.shah1989@gmail.com'

class RedirectError extends Error {
  constructor(readonly to: string) {
    super(`redirect:${to}`)
  }
}

vi.mock('next/navigation', () => ({
  redirect: (to: string) => {
    throw new RedirectError(to)
  },
}))

vi.mock('@/lib/supabase/env', () => ({ isSupabaseConfigured: () => true }))

vi.mock('@/lib/supabase/server', () => ({
  createServerSupabase: async () => ({
    auth: { getUser: async () => ({ data: { user: { email: SIGNED_IN } } }) },
  }),
}))

/** Load auth.ts fresh with a chosen NODE_ENV and a chosen "is the directory reachable" answer.
 *
 * ATLAS_GLOBAL_REQUIRE_AUTH=1 on every load: these tests are about what happens once a reader
 * HAS to sign in, and the board's default is now open (src/lib/openAccess.ts), where requireUser
 * returns before any of this. Without the stub every assertion below would pass for the wrong
 * reason — the fail-closed path would never run, and the test would be green and blind. */
async function loadAuth(nodeEnv: string, dbAvailable: boolean) {
  vi.resetModules()
  vi.stubEnv('NODE_ENV', nodeEnv)
  vi.stubEnv('ATLAS_GLOBAL_REQUIRE_AUTH', '1')
  vi.doMock('@/lib/db', () => ({ dbAvailable, db: () => { throw new Error('no directory') } }))
  return import('@/lib/auth')
}

beforeEach(() => {
  vi.unstubAllEnvs()
})

describe('requireUser when the invite list cannot be read', () => {
  it('refuses in production rather than admitting an unchecked session', async () => {
    const { requireUser } = await loadAuth('production', false)
    await expect(requireUser()).rejects.toThrow(RedirectError)
    await expect(requireUser()).rejects.toMatchObject({ to: '/login?reason=no-directory' })
  })

  it('still renders outside production, so a laptop with no database can boot', async () => {
    const { requireUser } = await loadAuth('development', false)
    const user = await requireUser()
    expect(user.email).toBe(SIGNED_IN)
    // The flag is the honest record that nobody checked this session.
    expect(user.allowlist_checked).toBe(false)
    expect(user.role).toBeNull()
  })
})
