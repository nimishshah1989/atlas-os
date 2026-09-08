// The board is OPEN by default and that is a deliberate, reviewed state, not a slip — so it is
// pinned here. Everything Global Atlas renders today is public market data: S&P 500 and ETF
// prices, returns, relative strength, one fund per country. No accounts, no positions, no PII.
//
// These tests exist so that the day someone adds a client page, a saved basket or an /admin
// surface, turning auth back on is a visible edit to a named assertion rather than a change
// nobody notices. If you are here because one of these went red: that is the alarm working.
import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadWith(value: string | undefined) {
  vi.resetModules()
  if (value === undefined) vi.stubEnv('ATLAS_GLOBAL_REQUIRE_AUTH', '')
  else vi.stubEnv('ATLAS_GLOBAL_REQUIRE_AUTH', value)
  return import('@/lib/openAccess')
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('authRequired', () => {
  it('is OFF when the variable is unset — the board serves public market data to anyone', async () => {
    const { authRequired } = await loadWith(undefined)
    expect(authRequired()).toBe(false)
  })

  it('is ON only for the exact string "1"', async () => {
    const { authRequired } = await loadWith('1')
    expect(authRequired()).toBe(true)
  })

  it.each(['0', 'true', 'yes', 'TRUE', ' 1', '1 '])(
    'treats %o as OFF — a mis-set variable must not build a wall nobody can pass',
    async (value) => {
      const { authRequired } = await loadWith(value)
      expect(authRequired()).toBe(false)
    },
  )
})
