// frontend/src/components/v6/sectors/__tests__/SectorRSRatioCharts.test.tsx
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
vi.mock('@/lib/v6/sectorTvSymbols', () => ({
  sectorRatioSymbol: () => 'NIFTY_IND_DEFENCE/NIFTY',
}))

import { SectorRSRatioCharts, resample } from '../SectorRSRatioCharts'
import type { RatioPoint } from '@/lib/queries/v6/sector_index_rs'

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
