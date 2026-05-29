import { describe, it, expect } from 'vitest'
import { generateChartCommentary } from '@/components/v6/stock-detail/ChartCommentary'

const BASE: Parameters<typeof generateChartCommentary>[0] = {
  state: null, dwellDays: null, stateSinceDate: null,
  ema20Ratio: null, volRatio63: null, extension: null, high52w: null, price: null,
}

describe('generateChartCommentary', () => {
  it('returns fallback when all inputs are null', () => {
    expect(generateChartCommentary(BASE)).toBe('Insufficient data for commentary.')
  })

  it('uses "Recently entered" for dwellDays <= 20', () => {
    const result = generateChartCommentary({ ...BASE, state: 'stage_2b', dwellDays: 14 })
    expect(result).toContain('Recently entered')
    expect(result).toContain('14 days ago')
  })

  it('uses "Confirmed in" for dwellDays 21-60', () => {
    expect(generateChartCommentary({ ...BASE, state: 'stage_2b', dwellDays: 45 })).toContain('Confirmed in')
  })

  it('uses "Established in" for dwellDays > 60', () => {
    expect(generateChartCommentary({ ...BASE, state: 'stage_2b', dwellDays: 120 })).toContain('Established in')
  })

  it('flags extension > 8%', () => {
    expect(generateChartCommentary({ ...BASE, ema20Ratio: 1.09 })).toContain('above EMA 20 — extended')
  })

  it('reports moderate extension without warning', () => {
    const r = generateChartCommentary({ ...BASE, ema20Ratio: 1.05 })
    expect(r).toContain('above EMA 20 — not overextended')
  })

  it('reports close-to-EMA within 3%', () => {
    expect(generateChartCommentary({ ...BASE, ema20Ratio: 1.02 })).toContain('close to EMA 20 — not extended')
  })

  it('reports below-EMA when ratio < 1', () => {
    expect(generateChartCommentary({ ...BASE, ema20Ratio: 0.97 })).toContain('below EMA 20 — needs to reclaim')
  })

  it('flags volume expanding', () => {
    expect(generateChartCommentary({ ...BASE, volRatio63: 1.5 })).toContain('Volume expanding')
  })

  it('flags volume fading', () => {
    expect(generateChartCommentary({ ...BASE, volRatio63: 0.7 })).toContain('Volume fading')
  })

  it('reports steady volume', () => {
    expect(generateChartCommentary({ ...BASE, volRatio63: 1.0 })).toContain('Volume steady')
  })

  it('combines all three sections', () => {
    const r = generateChartCommentary({ ...BASE, state: 'stage_2b', dwellDays: 30, ema20Ratio: 1.03, volRatio63: 1.4 })
    expect(r).toContain('Confirmed in')
    expect(r).toContain('close to EMA 20')
    expect(r).toContain('Volume expanding')
  })
})
