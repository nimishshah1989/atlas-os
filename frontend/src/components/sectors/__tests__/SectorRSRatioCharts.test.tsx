// frontend/src/components/sectors/__tests__/SectorRSRatioCharts.test.tsx
// Tests for the RS ratio charts: resampling logic + empty/render states.

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// AtlasLightweightChart mounts a canvas via lightweight-charts; stub it so the
// component tree renders in jsdom and we can assert structure.
vi.mock('@/components/charts/AtlasLightweightChart', () => ({
  AtlasLightweightChart: ({ title }: { title: string }) => (
    <div data-testid="lwc" data-title={title} />
  ),
}))
vi.mock('@/lib/sectorTvSymbols', () => ({
  sectorRatioSymbol: () => 'NIFTY_IND_DEFENCE/NIFTY',
}))

import { SectorRSRatioCharts, resample, mergeDailyIntraday, foldLiveIntoDaily } from '../SectorRSRatioCharts'
import type { RatioPoint } from '@/lib/queries/sector_index_rs'

describe('foldLiveIntoDaily', () => {
  const daily: RatioPoint[] = [
    { time: '2026-07-08', value: 1.0 },
    { time: '2026-07-09', value: 1.1 },
  ]
  // 2026-07-10 08:00 UTC == 13:30 IST (same calendar day in IST)
  const liveEpoch = Math.floor(Date.parse('2026-07-10T08:00:00Z') / 1000)

  it('returns the daily series unchanged when there is no live tail', () => {
    expect(foldLiveIntoDaily(daily, [])).toEqual(daily)
  })

  it('appends today (IST) with the latest live value so resample reflects it', () => {
    const folded = foldLiveIntoDaily(daily, [{ time: liveEpoch, value: 1.25 }])
    expect(folded[folded.length - 1]).toEqual({ time: '2026-07-10', value: 1.25 })
    // the current week's and month's last point now carries today's live value
    expect(resample(folded, 'W').at(-1)).toEqual({ time: '2026-07-10', value: 1.25 })
    expect(resample(folded, 'M').at(-1)).toEqual({ time: '2026-07-10', value: 1.25 })
  })
})

describe('mergeDailyIntraday', () => {
  const daily: RatioPoint[] = [
    { time: '2026-07-08', value: 1.0 },
    { time: '2026-07-09', value: 1.1 },
  ]
  const jul9midnight = Math.floor(Date.parse('2026-07-09T00:00:00Z') / 1000)

  it('returns the daily series unchanged when there is no intraday tail', () => {
    expect(mergeDailyIntraday(daily, [])).toEqual([
      { time: '2026-07-08', value: 1.0 },
      { time: '2026-07-09', value: 1.1 },
    ])
  })

  it('appends the intraday tail after the daily closes, ascending by time', () => {
    const tick = jul9midnight + 13 * 3600 // 2026-07-09 13:00 UTC
    const out = mergeDailyIntraday(daily, [{ time: tick, value: 1.2 }])
    expect(out.map((p) => p.value)).toEqual([1.0, 1.1, 1.2])
    // all numeric times, strictly ascending (lightweight-charts requires this)
    const times = out.map((p) => p.time as number)
    expect(times).toEqual([...times].sort((a, b) => a - b))
    expect(times[times.length - 1]).toBe(tick)
  })

  it('lets an intraday point override a daily point at the same epoch', () => {
    const out = mergeDailyIntraday(daily, [{ time: jul9midnight, value: 9.9 }])
    const jul9 = out.find((p) => p.time === jul9midnight)
    expect(jul9?.value).toBe(9.9)
    expect(out).toHaveLength(2) // no duplicate time
  })
})

describe('resample', () => {
  const daily: RatioPoint[] = [
    { time: '2026-01-05', value: 1.0 }, // Mon, ISO week 2
    { time: '2026-01-09', value: 1.1 }, // Fri, ISO week 2 (last of week)
    { time: '2026-01-12', value: 1.2 }, // Mon, ISO week 3
    { time: '2026-02-02', value: 1.3 }, // Feb
  ]

  it('weekly resample keeps the last point of each ISO week', () => {
    const w = resample(daily, 'W')
    expect(w.map((p) => p.value)).toEqual([1.1, 1.2, 1.3])
  })

  it('monthly resample keeps the last point of each calendar month', () => {
    const m = resample(daily, 'M')
    expect(m.map((p) => p.value)).toEqual([1.2, 1.3]) // Jan last = 1.2, Feb = 1.3
  })

  it('handles empty input', () => {
    expect(resample([], 'M')).toEqual([])
  })
})

describe('SectorRSRatioCharts', () => {
  it('renders three charts (Daily/Weekly/Monthly) when data is present', () => {
    const daily: RatioPoint[] = Array.from({ length: 10 }, (_, i) => ({
      time: `2026-01-${String(i + 1).padStart(2, '0')}`,
      value: 1 + i * 0.01,
    }))
    render(<SectorRSRatioCharts sectorName="Defence" indexCode="NIFTY IND DEFENCE" daily={daily} />)
    const charts = screen.getAllByTestId('lwc')
    expect(charts.map((c) => c.getAttribute('data-title'))).toEqual(['Daily', 'Weekly', 'Monthly'])
  })

  it('renders a placeholder when there is no price history', () => {
    render(<SectorRSRatioCharts sectorName="Defence" indexCode={null} daily={[]} />)
    expect(screen.queryAllByTestId('lwc')).toHaveLength(0)
    expect(screen.getByText(/chart unavailable/i)).toBeTruthy()
  })
})
