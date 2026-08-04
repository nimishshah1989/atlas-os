import { describe, it, expect } from 'vitest'
import { getFundEquityCurve } from '../fund_lens'

// Integration test — hits the real atlas_foundation. Runs on the laptop; skipped in CI.
// Every expected value is real produced output, verified 2026-08-04 (rule #0).
const hasDb = Boolean(process.env.ATLAS_DB_URL)

describe.skipIf(!hasDb)('getFundEquityCurve', () => {
  it('carries a benchmark level on 31 March, when NAVs exist but the index did not trade', async () => {
    // India's fiscal year end. AMCs must publish a NAV; the exchange is shut, so
    // index_prices has no row. Joining benchmarks on date equality dropped the fund's
    // most-looked-at month-end three times in five years (2024/2025/2026-03-31).
    const pts = await getFundEquityCurve('F0GBR06S3I') // ICICI Pru FMCG Gr
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
    const pts = await getFundEquityCurve('F0GBR06S3I')
    expect(pts.length).toBeGreaterThan(100)
    expect(pts.filter((p) => p.nifty50 == null || p.nifty500 == null)).toEqual([])
  })
})
