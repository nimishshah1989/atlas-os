// Smoke test for getMarketRegimePage — locks JSONB-parsed shape from
// atlas.mv_market_regime_landing.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getMarketRegimePage } from '../market-regime'

describe('getMarketRegimePage', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns null fallback when MV has no rows', async () => {
    sqlMock.mockResolvedValueOnce([])
    const p = await getMarketRegimePage()
    expect(p).toBeNull()
  })

  it('parses all JSONB sections + numeric coercion', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        as_of_date: '2026-05-22',
        regime_state: 'Constructive',
        deployment_multiplier: '0.7000',
        days_in_regime: 14,
        entered_date: '2026-05-08',
        prior_regime_state: 'Cautious',
        typical_length_days: 21,
        liquid_bees_yield_pct: '6.85',
        refreshed_at: '2026-05-23T14:30:00Z',
        next_state_probs: {
          'Risk-On': 34,
          'Risk-Off': 2,
          Constructive: 56,
          DISLOCATION_SUSPENDED: 8,
        },
        recent_60d_segments: [
          { state: 'DISLOCATION_SUSPENDED', days: 20 },
          { state: 'Constructive', days: 14 },
        ],
        twelve_week_journey: [
          {
            week_start: '2026-02-23',
            regime_state: 'Cautious',
            breadth_pct: 0.4008,
            india_vix: 13.7,
          },
        ],
        cells_favored: [
          {
            cell_id: 'cce786c1-e323-4635-ac86-f7cff1f0720b',
            cap_tier: 'Large',
            tenure: '12m',
            action: 'NEGATIVE',
            confidence: 'HIGH',
            display_name: 'Large 12m AVOID signal',
            explain_text: 'Large-cap 12-month structural failure.',
            predicted_excess: -0.177074,
            stocks_firing_today: 9,
          },
        ],
        conviction_stocks: [
          {
            symbol: 'ATLANTAELE',
            company_name: 'Atlanta Electricals Limited',
            sector: 'Capital Goods',
            cap_tier: 'Micro',
            action: 'POSITIVE',
            cell_name: 'Mid 12m BUY signal',
            confidence: 13,
            predicted_excess: 0.603,
            is_new_today: true,
          },
        ],
        conviction_funds: [
          {
            scheme_code: 'F00001RZRD',
            fund_name: 'Capitalmind Flexi Cap Dir Gr',
            category: 'India Fund Flexi Cap',
            plan_type: 'Regular',
            composite: 69.44,
            quartile: 'Q1',
            recommendation: 'HOLD',
            is_atlas_leader: false,
          },
        ],
        conviction_etfs: [
          {
            ticker: 'HEALTHIETF',
            etf_name: 'Nippon India ETF Nifty Healthcare',
            category: 'sector',
            underlying_sector: 'Healthcare',
            action: 'POSITIVE',
            cell_name: 'Large 6m BUY signal',
            composite: 61.64,
            predicted_excess: null,
          },
        ],
        deployment_defaults: {
          'Risk-On': 0.6,
          Cautious: 0.4,
          Elevated: 0.5,
          'Risk-Off': 0.3,
        },
      },
    ])

    const p = await getMarketRegimePage()
    expect(p).not.toBeNull()
    if (!p) return

    // Scalar fields
    expect(p.as_of_date).toBe('2026-05-22')
    expect(p.regime_state).toBe('Constructive')
    expect(p.deployment_multiplier).toBeCloseTo(0.7)
    expect(p.days_in_regime).toBe(14)
    expect(p.entered_date).toBe('2026-05-08')
    expect(p.prior_regime_state).toBe('Cautious')
    expect(p.typical_length_days).toBe(21)
    expect(p.liquid_bees_yield_pct).toBeCloseTo(6.85)

    // JSONB arrays
    expect(p.twelve_week_journey).toHaveLength(1)
    expect(p.twelve_week_journey[0].week_start).toBe('2026-02-23')
    expect(p.twelve_week_journey[0].breadth_pct).toBeCloseTo(0.4008)

    expect(p.recent_60d_segments).toHaveLength(2)
    expect(p.recent_60d_segments[0].state).toBe('DISLOCATION_SUSPENDED')
    expect(p.recent_60d_segments[0].days).toBe(20)

    expect(p.cells_favored).toHaveLength(1)
    expect(p.cells_favored[0].cap_tier).toBe('Large')
    expect(p.cells_favored[0].confidence).toBe('HIGH')
    expect(p.cells_favored[0].stocks_firing_today).toBe(9)
    expect(p.cells_favored[0].predicted_excess).toBeCloseTo(-0.177074)

    expect(p.conviction_stocks).toHaveLength(1)
    expect(p.conviction_stocks[0].symbol).toBe('ATLANTAELE')
    expect(p.conviction_stocks[0].is_new_today).toBe(true)

    expect(p.conviction_funds).toHaveLength(1)
    expect(p.conviction_funds[0].scheme_code).toBe('F00001RZRD')
    expect(p.conviction_funds[0].quartile).toBe('Q1')

    expect(p.conviction_etfs).toHaveLength(1)
    expect(p.conviction_etfs[0].ticker).toBe('HEALTHIETF')
    expect(p.conviction_etfs[0].underlying_sector).toBe('Healthcare')

    // JSONB objects
    expect(p.next_state_probs.Constructive).toBe(56)
    expect(p.next_state_probs['Risk-Off']).toBe(2)

    expect(p.deployment_defaults['Risk-On']).toBeCloseTo(0.6)
    expect(p.deployment_defaults.Cautious).toBeCloseTo(0.4)
  })

  it('handles null JSONB sections gracefully (returns empty arrays/objects)', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        as_of_date: '2026-05-22',
        regime_state: 'Risk-Off',
        deployment_multiplier: '0.3000',
        days_in_regime: 1,
        entered_date: '2026-05-22',
        prior_regime_state: null,
        typical_length_days: null,
        liquid_bees_yield_pct: null,
        refreshed_at: null,
        next_state_probs: null,
        recent_60d_segments: null,
        twelve_week_journey: null,
        cells_favored: null,
        conviction_stocks: null,
        conviction_funds: null,
        conviction_etfs: null,
        deployment_defaults: null,
      },
    ])

    const p = await getMarketRegimePage()
    expect(p).not.toBeNull()
    if (!p) return

    expect(p.regime_state).toBe('Risk-Off')
    expect(p.liquid_bees_yield_pct).toBeNull()
    expect(p.twelve_week_journey).toEqual([])
    expect(p.cells_favored).toEqual([])
    expect(p.conviction_stocks).toEqual([])
    expect(p.conviction_funds).toEqual([])
    expect(p.conviction_etfs).toEqual([])
    expect(p.recent_60d_segments).toEqual([])
    expect(p.next_state_probs).toEqual({})
    expect(p.deployment_defaults).toEqual({})
  })
})
