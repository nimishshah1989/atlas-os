import { describe, expect, it } from 'vitest'
import { formatUsdCompact } from '@/lib/format'

// Every figure below is a real ADV$ or AUM from the live board's own /etfs payload, read off the
// screenshot the FM sent and from docs/global/reports/adv_usd_2026-09-03.md.
describe('a traded value fits its column instead of being cut in half', () => {
  it('renders the real ADV$ figures the table was truncating', () => {
    expect(formatUsdCompact('129145821')).toBe('$129M')   // CIBR, shown as "$129,1…"
    expect(formatUsdCompact('37850000')).toBe('$37.8M')   // ARTY, shown as "$37,85…"
    expect(formatUsdCompact('1770000000')).toBe('$1.7B')  // THNQ, shown as "$1,770,…"
    expect(formatUsdCompact('13250000')).toBe('$13.2M')   // IVES
  })

  it('keeps three significant figures: a tenth while the whole part is one or two digits', () => {
    // "$37.8M" is six characters and says more than "$37M"; "$713M" is five and a tenth would
    // add nothing. The rule is significant figures, not a fixed number of decimals.
    expect(formatUsdCompact('1845000000')).toBe('$1.8B')
    expect(formatUsdCompact('12800000')).toBe('$12.8M')
    expect(formatUsdCompact('713056335')).toBe('$713M')   // the P99 of the real ETF distribution
  })

  it('never rounds a real amount down to nothing', () => {
    // $47,591 is the P10 of the real ETF distribution. "$0M" would be a lie about a real fund.
    expect(formatUsdCompact('47591')).toBe('$47.5K')
    expect(formatUsdCompact('999')).toBe('$999')
    // A round million drops the tenth rather than printing "$1.0M": a trailing zero is a claim
    // of precision the figure does not have.
    expect(formatUsdCompact('1000000')).toBe('$1M')
  })

  it('says nothing when there is nothing, and keeps a sign when there is one', () => {
    expect(formatUsdCompact(null)).toBe('—')
    expect(formatUsdCompact('')).toBe('—')
    expect(formatUsdCompact('-2500000')).toBe('-$2.5M')
  })
})
