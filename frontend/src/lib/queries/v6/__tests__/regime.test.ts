// Smoke test for getCurrentRegime.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getCurrentRegime } from '../regime'

describe('getCurrentRegime', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns the latest row + reversed history strip', async () => {
    sqlMock
      .mockResolvedValueOnce([
        {
          date: '2026-05-22',
          regime_state: 'Cautious',
          deployment_multiplier: '0.4',
          pct_above_ema_50: '0.5622',
          pct_in_strong_states: '0.0723',
          pct_weinstein_pass: '0.3313',
        },
      ])
      .mockResolvedValueOnce([
        // descending date order as returned by DB
        { date: '2026-05-22', pct_above_ema_50: '0.5622', regime_state: 'Cautious' },
        { date: '2026-05-21', pct_above_ema_50: '0.5400', regime_state: 'Cautious' },
      ])

    const r = await getCurrentRegime()
    expect(r.regime_state).toBe('Cautious')
    expect(r.deployment_pct).toBe(40)
    expect(r.pct_above_ema_50).toBeCloseTo(0.5622)
    // history must be reversed → oldest first for sparkline
    expect(r.history[0].date).toBe('2026-05-21')
    expect(r.history[1].date).toBe('2026-05-22')
    expect(r.cells_favored).toEqual([])
  })

  it('returns neutral fallback when no rows exist', async () => {
    sqlMock.mockResolvedValueOnce([]).mockResolvedValueOnce([])
    const r = await getCurrentRegime()
    expect(r.regime_state).toBe('Neutral')
    expect(r.deployment_pct).toBe(50)
    expect(r.history).toEqual([])
  })
})
