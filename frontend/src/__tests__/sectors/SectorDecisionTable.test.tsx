import { describe, it, expect } from 'vitest'

const RS_STATE_ORDER: Record<string, number> = {
  Leader:        1,
  Strong:        2,
  Emerging:      3,
  Consolidating: 4,
  Average:       5,
  Weak:          6,
  Laggard:       7,
}

function sortByRsState(a: string | null, b: string | null): number {
  const ao = RS_STATE_ORDER[a ?? ''] ?? 99
  const bo = RS_STATE_ORDER[b ?? ''] ?? 99
  return ao - bo
}

function topdownAgrees(tdRs: string | null, buRs: string | null): boolean | null {
  if (tdRs == null || buRs == null) return null
  return Math.sign(parseFloat(tdRs)) === Math.sign(parseFloat(buRs))
}

function computeLeadingRRGCount(
  sectors: Array<{ rs: string | null; momentum: string | null }>,
): number {
  const vals = sectors
    .map(s => parseFloat(s.rs ?? 'NaN'))
    .filter(v => !isNaN(v))
  const mean = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
  return sectors.filter(s => {
    const rs  = parseFloat(s.rs  ?? 'NaN')
    const mom = parseFloat(s.momentum ?? 'NaN')
    return !isNaN(rs) && !isNaN(mom) && (rs - mean) > 0 && mom > 0
  }).length
}

describe('sortByRsState', () => {
  it('Leader sorts before Strong', () => {
    expect(sortByRsState('Leader', 'Strong')).toBeLessThan(0)
  })
  it('Laggard sorts after Weak', () => {
    expect(sortByRsState('Laggard', 'Weak')).toBeGreaterThan(0)
  })
  it('null sorts last', () => {
    expect(sortByRsState(null, 'Leader')).toBeGreaterThan(0)
  })
})

describe('topdownAgrees', () => {
  it('returns true when both positive', () => {
    expect(topdownAgrees('0.04', '0.03')).toBe(true)
  })
  it('returns false when signs differ', () => {
    expect(topdownAgrees('-0.02', '0.05')).toBe(false)
  })
  it('returns null when either is null', () => {
    expect(topdownAgrees(null, '0.03')).toBeNull()
  })
})

describe('computeLeadingRRGCount', () => {
  it('counts sectors with above-mean RS and positive momentum', () => {
    const sectors = [
      { rs: '0.10', momentum: '0.005' },
      { rs: '0.05', momentum: '-0.002' },
      { rs: '-0.04', momentum: '0.001' },
    ]
    expect(computeLeadingRRGCount(sectors)).toBe(1)
  })
  it('returns 0 when all sectors are lagging', () => {
    const sectors = [
      { rs: '-0.05', momentum: '-0.003' },
      { rs: '-0.02', momentum: '-0.001' },
    ]
    expect(computeLeadingRRGCount(sectors)).toBe(0)
  })
})
