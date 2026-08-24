import { describe, it, expect } from 'vitest'

// Integration test — hits the real atlas_foundation. Runs on the laptop; skipped in CI.
// Every expected value is real produced output, verified 2026-08-04 (rule #0).
const hasDb = Boolean(process.env.ATLAS_DB_URL)

// Imported lazily, NOT at the top: lib/db.ts throws at module load when ATLAS_DB_URL is
// unset, so a static import fails the whole suite in CI instead of skipping it —
// describe.skipIf only skips the tests, never the imports above it.
const q = hasDb ? await import('../fund_lens') : null

/** A guard, not a cast — a test that somehow runs without a DB says so instead of
 *  dying on `undefined is not a function`. */
function db(): NonNullable<typeof q> {
  if (!q) throw new Error('integration test ran without ATLAS_DB_URL — it should have skipped')
  return q
}

describe.skipIf(!hasDb)('getFundEquityCurve', () => {
  it('carries a benchmark level on 31 March, when NAVs exist but the index did not trade', async () => {
    // India's fiscal year end. AMCs must publish a NAV; the exchange is shut, so
    // index_prices has no row. Joining benchmarks on date equality dropped the fund's
    // most-looked-at month-end three times in five years (2024/2025/2026-03-31).
    const pts = await db().getFundEquityCurve('F0GBR06S3I') // ICICI Pru FMCG Gr
    const fy = pts.filter((p) => p.d.endsWith('-03-31'))
    expect(fy.length).toBeGreaterThanOrEqual(2)
    for (const p of fy) {
      expect(p.nifty50, `nifty50 missing on ${p.d}`).not.toBeNull()
      expect(p.nifty500, `nifty500 missing on ${p.d}`).not.toBeNull()
    }
    // 2026-03-31 must carry the 2026-03-30 close, the last one on or before it.
    const mar26 = pts.find((p) => p.d === '2026-03-31')
    if (mar26) expect(mar26.nifty50).toBeCloseTo(22331.4, 1)
  })

  it('never leaves a benchmark null on any date it returns', async () => {
    const pts = await db().getFundEquityCurve('F0GBR06S3I')
    expect(pts.length).toBeGreaterThan(100)
    expect(pts.filter((p) => p.nifty50 == null || p.nifty500 == null)).toEqual([])
  })
})

describe.skipIf(!hasDb)('getFundActiveMovement', () => {
  it('counts the leaders a manager actually added and dropped', async () => {
    // lead is the 0/1 leader flag from v_stock_leader — a leader has lead = 1. Counting
    // on lead >= 2 (the retired 4-lens tally) made both headline numbers structurally 0
    // for every fund on the board. Verified 2026-08-23 against atlas_foundation: this
    // fund's latest two holdings snapshots add 4 leaders and drop 2.
    const m = await db().getFundActiveMovement('F0000142R9') // Motilal Oswal Nifty 500 Reg Gr
    expect(m).not.toBeNull()
    expect(m!.leaders_added).toBeGreaterThan(0)
    expect(m!.leaders_dropped).toBeGreaterThan(0)
    // and the flag itself only ever takes the two values the count is built on
    for (const mv of [...m!.added, ...m!.exited]) expect([0, 1]).toContain(mv.lead)
  })
})
