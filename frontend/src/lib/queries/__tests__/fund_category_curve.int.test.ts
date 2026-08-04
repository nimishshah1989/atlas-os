import { describe, it, expect } from 'vitest'

// Integration test — hits the real atlas_foundation. Runs on the laptop (point ATLAS_DB_URL
// at it); skipped in CI where there is no DB. Per rule #0 every expected value below is real
// produced output, verified 2026-08-04 against the universe-scoped query.
const hasDb = Boolean(process.env.ATLAS_DB_URL)

// Imported lazily, NOT at the top: lib/db.ts throws at module load when ATLAS_DB_URL is
// unset, so a static import fails the whole suite in CI instead of skipping it —
// describe.skipIf only skips the tests, never the imports above it.
const q = hasDb ? await import('../fund_category_curve') : null

/** A guard, not a cast — a test that somehow runs without a DB says so instead of
 *  dying on `undefined is not a function`. */
function db(): NonNullable<typeof q> {
  if (!q) throw new Error('integration test ran without ATLAS_DB_URL — it should have skipped')
  return q
}

describe.skipIf(!hasDb)('getCategoryComposite', () => {
  it('does not step the curve when a fund enters mid-window', async () => {
    // Kotak Energy Opportunities (F00001Q785) reports its first NAV on 2025-05-02. That day
    // it must contribute NOTHING — no previous NAV means no return — so the count stays at 3.
    // It joins the average on 2025-05-05, taking the count to 4. If a new fund's arrival ever
    // moves the composite, the aggregation is averaging levels rather than returns.
    const rows = await db().getCategoryComposite('India Fund Sector - Energy', '2025-04-28', '2025-05-07')
    expect(rows.map((r) => [r.d, Number(r.v.toFixed(6)), r.n])).toEqual([
      ['2025-04-28', 100.000000, 0],
      ['2025-04-29', 100.007304, 3],
      ['2025-04-30', 99.684253, 3],
      ['2025-05-02', 99.605574, 3], // Kotak's first NAV — no return, no effect
      ['2025-05-05', 100.464847, 4], // now contributing
      ['2025-05-06', 99.032088, 4],
      ['2025-05-07', 99.662856, 4],
    ])
  })

  it('does not step the curve when a fund exits mid-window', async () => {
    // Sundaram Fin Services Opp Instl (F00000NS2W) stops reporting after 2025-01-22 — a real
    // institutional share class wind-down, not a tracking gap. The count drops 23 -> 22 and
    // the curve carries on without a jump.
    const rows = await db().getCategoryComposite(
      'India Fund Sector - Financial Services', '2025-01-17', '2025-01-28')
    expect(rows.map((r) => [r.d, Number(r.v.toFixed(6)), r.n])).toEqual([
      ['2025-01-17', 100.000000, 0],
      ['2025-01-20', 101.042533, 23],
      ['2025-01-21', 99.258902, 23],
      ['2025-01-22', 99.162256, 23], // Sundaram's last NAV
      ['2025-01-23', 99.214115, 22],
      ['2025-01-24', 98.402350, 22],
      ['2025-01-27', 97.168306, 22],
      ['2025-01-28', 98.339696, 22],
    ])
  })

  it('drops a fund from the average on a day it did not report, rather than reading it flat', async () => {
    // Real NAV gaps: SBI Energy has no 2026-03-30 NAV, and on 2026-04-01 only two of the four
    // funds reported. A missing NAV must yield no return for that fund, never a zero return.
    const rows = await db().getCategoryComposite('India Fund Sector - Energy', '2026-03-30', '2026-04-07')
    expect(rows.map((r) => [r.d, Number(r.v.toFixed(6)), r.n])).toEqual([
      ['2026-03-30', 100.000000, 0],
      ['2026-03-31', 99.994732, 3], // SBI Energy has no 03-30 NAV -> contributes no return
      ['2026-04-01', 101.564416, 2], // two funds missing entirely — a real gap
      ['2026-04-02', 102.179894, 4],
      ['2026-04-06', 102.232807, 4],
      ['2026-04-07', 102.511006, 4],
    ])
  })

  it('equals the fund itself when the category holds exactly one fund', async () => {
    // "India Fund Sector - FMCG" is ICICI Pru FMCG Gr alone, so the composite must be that
    // fund's own rebased NAV: 100 × 413.69 / 407.80 = 101.444335 on 2026-06-10.
    const rows = await db().getCategoryComposite('India Fund Sector - FMCG', '2026-06-01', '2026-06-10')
    expect(rows[0]).toMatchObject({ d: '2026-06-01', n: 0 })
    expect(rows[0].v).toBeCloseTo(100, 9)
    expect(rows.at(-1)!.d).toBe('2026-06-10')
    expect(rows.at(-1)!.v).toBeCloseTo(101.444335, 5)
    expect(rows.every((r) => r.n <= 1)).toBe(true)
  })

  it('fills benchmark closes on dates the index did not trade', async () => {
    // index_prices has no NIFTY FMCG row for 2026-03-31 (fiscal year end — AMCs publish a NAV,
    // the exchange is shut). The as-of join must supply the 2026-03-30 close of 45538.65.
    const rows = await db().getCategoryComposite('India Fund Sector - FMCG', '2026-03-31', '2026-03-31')
    expect(rows).toHaveLength(1)
    expect(rows[0].catIndex).toBeCloseTo(45538.65, 2)
  })

  it('returns an empty array for a range with no NAV data', async () => {
    expect(await db().getCategoryComposite('India Fund Sector - FMCG', '1990-01-01', '1990-01-31')).toEqual([])
  })

  it('excludes funds outside the curated universe, whose NAVs no longer refresh', async () => {
    // Groww BSE Power ETF FOF sits in the Energy category with NAV history to 2026-04-02, but
    // it is not in atlas_universe_funds, so ingest_nav.py stopped refreshing it. Counting it
    // would stage a phantom "exit" on a date the fund never closed.
    const rows = await db().getCategoryComposite('India Fund Sector - Energy', '2026-04-01', '2026-04-07')
    expect(rows.every((r) => r.n <= 4)).toBe(true)
  })
})

describe.skipIf(!hasDb)('getCategoryOptions', () => {
  it('returns a benchmark mapping for every category it offers', async () => {
    const opts = await db().getCategoryOptions()
    expect(opts.length).toBeGreaterThanOrEqual(15)
    for (const o of opts) expect(db().CATEGORY_INDEX[o.category]).toBeDefined()
  })

  it('offers only categories whose NAVs are actually current', async () => {
    // Every universe fund refreshes nightly, so no offered category may be stale. This is the
    // regression guard: if a category ever goes quiet, this fails rather than the page quietly
    // drawing a frozen curve.
    const opts = await db().getCategoryOptions()
    const newest = opts.reduce((a, o) => (o.lastNav && o.lastNav > a ? o.lastNav : a), '')
    for (const o of opts) {
      expect(o.lastNav, `${o.category} has no NAV`).not.toBeNull()
      expect(o.lastNav! >= newest.slice(0, 8) + '01', `${o.category} stale at ${o.lastNav}`).toBe(true)
    }
  })

  it('no longer offers the frozen categories that never refresh', async () => {
    // Index Funds (245), Focused Fund (30) and Equity-ESG (12) carry NAV history but sit
    // outside the curated universe, so their NAVs stopped in April/May 2026. They are excluded
    // until they are curated in — see docs/superpowers/specs/2026-08-04-fund-category-compare.
    const names = (await db().getCategoryOptions()).map((o) => o.category)
    expect(names).not.toContain('India Fund Index Funds')
    expect(names).not.toContain('India Fund Focused Fund')
    expect(names).not.toContain('India Fund Equity - ESG')
  })
})
