// Smoke test for getCurrentRegime + getRegimeDetail.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getCurrentRegime, getRegimeDetail } from '../regime'

// ---------------------------------------------------------------------------
// getCurrentRegime tests (unchanged)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// getRegimeDetail tests (new for D.9)
// ---------------------------------------------------------------------------

describe('getRegimeDetail', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns empty/null fallback when no rows', async () => {
    sqlMock.mockResolvedValueOnce([])
    const d = await getRegimeDetail()
    expect(d.regime_state).toBe('Neutral')
    expect(d.deployment_multiplier).toBeNull()
    expect(d.days_in_regime).toBe(0)
    expect(d.flip_probability_5d).toBeNull()
    expect(d.journey).toEqual([])
    expect(d.inputs).toEqual([])
    expect(d.as_of).toBeNull()
  })

  it('computes days_in_regime streak from descending rows', async () => {
    // 3 rows: latest 2 share the same state, 3rd is different
    sqlMock.mockResolvedValueOnce([
      {
        date: '2026-05-22',
        regime_state: 'Constructive',
        deployment_multiplier: '0.7000',
        smallcap_rs_z: '0.4500',
        breadth_pct_above_200dma: '0.6200',
        vix_percentile: '0.3000',
        cross_sectional_dispersion: '0.023456',
      },
      {
        date: '2026-05-21',
        regime_state: 'Constructive',
        deployment_multiplier: '0.7000',
        smallcap_rs_z: '0.4200',
        breadth_pct_above_200dma: '0.6100',
        vix_percentile: '0.3100',
        cross_sectional_dispersion: '0.022000',
      },
      {
        date: '2026-05-20',
        regime_state: 'Cautious', // streak breaks here
        deployment_multiplier: '0.4000',
        smallcap_rs_z: '-0.1000',
        breadth_pct_above_200dma: '0.4800',
        vix_percentile: '0.6000',
        cross_sectional_dispersion: '0.031000',
      },
    ])

    const d = await getRegimeDetail()
    expect(d.regime_state).toBe('Constructive')
    expect(d.days_in_regime).toBe(2)
    expect(d.deployment_multiplier).toBe('0.7000')
    // flip_probability_5d is always null (column not on table)
    expect(d.flip_probability_5d).toBeNull()
    // journey is oldest→newest (reversed)
    expect(d.journey[0].date).toBe('2026-05-20')
    expect(d.journey[2].date).toBe('2026-05-22')
    // inputs populated
    expect(d.inputs[2].smallcap_rs_z).toBeCloseTo(0.45)
    expect(d.as_of).toBe('2026-05-22')
  })

  it('handles all-null input columns gracefully', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        date: '2026-05-22',
        regime_state: 'Risk-Off',
        deployment_multiplier: '0.0000',
        smallcap_rs_z: null,
        breadth_pct_above_200dma: null,
        vix_percentile: null,
        cross_sectional_dispersion: null,
      },
    ])

    const d = await getRegimeDetail()
    expect(d.regime_state).toBe('Risk-Off')
    expect(d.days_in_regime).toBe(1)
    expect(d.inputs[0].smallcap_rs_z).toBeNull()
    expect(d.inputs[0].breadth_pct_above_200dma).toBeNull()
    expect(d.inputs[0].vix_percentile).toBeNull()
    expect(d.inputs[0].cross_sectional_dispersion).toBeNull()
  })
})
