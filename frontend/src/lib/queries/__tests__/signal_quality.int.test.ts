import { describe, it, expect } from 'vitest'

// Integration test — hits the real atlas_foundation.atlas_signal_ic. Runs on the laptop;
// skipped in CI. Every expected value below is REAL produced output read out of the
// journal table on 2026-08-25 (rule #0: no synthetic data, tests included).
const hasDb = Boolean(process.env.ATLAS_DB_URL)

// Imported lazily, NOT at the top: lib/db.ts throws at module load when ATLAS_DB_URL is
// unset, so a static import fails the whole suite in CI instead of skipping it.
const q = hasDb ? await import('../signal_quality') : null

function db(): NonNullable<typeof q> {
  if (!q) throw new Error('integration test ran without ATLAS_DB_URL — it should have skipped')
  return q
}

describe.skipIf(!hasDb)('getSignalQuality', () => {
  it('returns every lens in both eras, with cap_coverage attached', async () => {
    const rows = await db().getSignalQuality()
    // 7 lenses × 3 horizons × 5 cohorts × 2 eras
    expect(rows.length).toBe(210)
    const lenses = new Set(rows.map((r) => r.lens))
    expect([...lenses].sort()).toEqual([
      'catalyst', 'composite', 'flow', 'fundamental', 'policy', 'technical', 'valuation',
    ])
    expect([...new Set(rows.map((r) => r.era))].sort()).toEqual(['narrow', 'wide'])
    // cap_coverage is the qualifier the page must show next to every cap-band figure.
    expect(rows.every((r) => r.cap_coverage != null)).toBe(true)
  })

  it('carries the real large-cap 63-day headline, not a rounded copy', async () => {
    const rows = await db().getSignalQuality()
    const pick = (lens: string, era: string) =>
      rows.find((r) => r.lens === lens && r.era === era && r.cohort === 'large' && r.horizon_d === 63)
    const policy = pick('policy', 'wide')
    expect(policy?.mean_ic).toBeCloseTo(0.06387, 5)
    expect(policy?.hit_rate).toBeCloseTo(0.6739, 4)
    expect(policy?.n_dates).toBe(1343)
    // the wide era's cap bands saw ~59% of the cross-section — v_stock_cap has no date dimension
    expect(policy?.cap_coverage).toBeCloseTo(0.5947, 4)
    expect(pick('composite', 'narrow')?.mean_ic).toBeCloseTo(-0.05145, 5)
  })
})

describe.skipIf(!hasDb)('classifySignal', () => {
  it('grades the real policy and composite rows the FM has to act on', async () => {
    const rows = await db().getSignalQuality()
    const pick = (lens: string, era: string) =>
      rows.find((r) => r.lens === lens && r.era === era && r.cohort === 'large' && r.horizon_d === 63)!
    // policy wide: IC +0.064, hit 67% — the only lens that clears the bar in both eras
    expect(db().classifySignal(pick('policy', 'wide'))).toBe('carries signal')
    expect(db().classifySignal(pick('policy', 'narrow'))).toBe('carries signal')
    // composite wide: IC +0.0003 — the weakest cell on the page, and it must stay visible
    expect(db().classifySignal(pick('composite', 'wide'))).toBe('no evidence')
    // technical narrow: IC -0.073 on a 32% hit rate — real magnitude, wrong direction
    expect(db().classifySignal(pick('technical', 'narrow'))).toBe('weak')
  })

  it('treats an unmeasurable IC as no evidence, never as a zero reading', () => {
    // A cohort that is one tie block has no ordering to correlate: NULL, not 0.00.
    expect(db().classifySignal({ mean_ic: null, hit_rate: null })).toBe('no evidence')
  })
})

describe.skipIf(!hasDb)('displaySpread', () => {
  it('suppresses the spreads corrupted by the sub-₹1 close_adj defect', async () => {
    const rows = await db().getSignalQuality()
    // 86 instruments carry 28,507 sub-₹1 close_adj rows before June 2024 (PRIVISCL reads
    // ₹0.05 on 2020-03-23 with adj_factor = 1.0). Rank-IC is immune; the arithmetic mean
    // decile spread is not — this cell reads +2811%.
    const corrupt = rows.find(
      (r) => r.lens === 'composite' && r.era === 'wide' && r.cohort === 'small' && r.horizon_d === 126,
    )!
    expect(corrupt.mean_spread).toBeGreaterThan(28)
    expect(db().displaySpread(corrupt.mean_spread)).toBeNull()
    // a spread inside the plausible band survives
    const sane = rows.find(
      (r) => r.lens === 'policy' && r.era === 'wide' && r.cohort === 'large' && r.horizon_d === 63,
    )!
    expect(db().displaySpread(sane.mean_spread)).toBeCloseTo(0.065534, 6)
    expect(db().displaySpread(null)).toBeNull()
  })
})
