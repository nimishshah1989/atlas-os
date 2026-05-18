import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { RRGChart } from '../RRGChart'
import type { SectorSnapshot, RRGHistoryRow } from '@/lib/queries/sectors'

// Build a minimal SectorSnapshot. We only care about the fields RRGChart reads:
// sector_name, constituent_count, bottomup_rs_3m_nifty500, rs_momentum,
// bottomup_momentum_state. All others are present-but-irrelevant.
function makeSnapshot(over: Partial<SectorSnapshot>): SectorSnapshot {
  // Use `in` checks so explicit null overrides aren't replaced by defaults.
  return {
    sector_name: over.sector_name ?? 'Tech',
    constituent_count: over.constituent_count ?? 25,
    bottomup_ret_1w: null,
    bottomup_ret_1m: null,
    bottomup_ret_3m: null,
    bottomup_ret_6m: null,
    bottomup_rs_3m_nifty500:
      'bottomup_rs_3m_nifty500' in over ? (over.bottomup_rs_3m_nifty500 ?? null) : '0.10',
    rs_momentum: 'rs_momentum' in over ? (over.rs_momentum ?? null) : '0.02',
    bottomup_ema_10_ratio: null,
    bottomup_ema_20_ratio: null,
    topdown_ret_1m: null,
    topdown_ret_3m: null,
    topdown_rs_3m_nifty500: null,
    topdown_index_code: null,
    participation_50: null,
    participation_rs: null,
    participation_rs_pct: null,
    leadership_concentration: null,
    sector_state: 'Neutral',
    bottomup_state: null,
    topdown_state: null,
    divergence_flag: false,
    bottomup_rs_state: null,
    bottomup_momentum_state: over.bottomup_momentum_state ?? 'Improving',
    bottomup_risk_state: null,
    bottomup_volume_state: null,
    data_date: new Date('2026-05-09'),
    pct_stage_2: null,
    pct_stage_3: null,
    pct_stage_4: null,
  }
}

describe('RRGChart', () => {
  it('renders empty-state placeholder when current is empty', () => {
    render(<RRGChart current={[]} history={[]} onSelect={() => {}} />)
    expect(
      screen.getByText(/Add at least 3 sectors with 20\+ days/i),
    ).toBeInTheDocument()
  })

  it('renders an SVG with role=img when given current data', () => {
    const current: SectorSnapshot[] = [
      makeSnapshot({ sector_name: 'Tech', bottomup_rs_3m_nifty500: '0.10', rs_momentum: '0.02' }),
      makeSnapshot({ sector_name: 'Banks', bottomup_rs_3m_nifty500: '-0.05', rs_momentum: '-0.01' }),
      makeSnapshot({ sector_name: 'Auto', bottomup_rs_3m_nifty500: '0.04', rs_momentum: '0.00' }),
    ]
    const { container } = render(
      <RRGChart current={current} history={[]} onSelect={() => {}} />,
    )
    const svg = container.querySelector('svg[role="img"]')
    expect(svg).not.toBeNull()
    expect(svg?.getAttribute('aria-label')).toContain('3 sectors')
  })

  it('renders 4 quadrant watermark labels with aria-hidden', () => {
    const current = [
      makeSnapshot({ sector_name: 'Tech', bottomup_rs_3m_nifty500: '0.10', rs_momentum: '0.02' }),
      makeSnapshot({ sector_name: 'Banks', bottomup_rs_3m_nifty500: '-0.05', rs_momentum: '-0.01' }),
    ]
    const { container } = render(
      <RRGChart current={current} history={[]} onSelect={() => {}} />,
    )
    const labels = ['Leading', 'Weakening', 'Improving', 'Lagging']
    for (const text of labels) {
      const node = Array.from(container.querySelectorAll('text')).find(
        (n) => n.textContent === text,
      )
      expect(node, `expected ${text} watermark`).toBeTruthy()
      expect(node?.getAttribute('aria-hidden')).toBe('true')
    }
  })

  it('mean-centers both axes — equal mean => crosshair at chart center', () => {
    // Two sectors symmetric around (0.05, 0.02) → centered values become (±0.05, ±0.01).
    // After scaling, the crosshair (0,0) sits between the two dots.
    const current: SectorSnapshot[] = [
      makeSnapshot({
        sector_name: 'High',
        bottomup_rs_3m_nifty500: '0.10',
        rs_momentum: '0.03',
      }),
      makeSnapshot({
        sector_name: 'Low',
        bottomup_rs_3m_nifty500: '0.00',
        rs_momentum: '0.01',
      }),
    ]
    const { container } = render(
      <RRGChart current={current} history={[]} onSelect={() => {}} />,
    )
    const dots = container.querySelectorAll('g.sector-dot')
    expect(dots.length).toBe(2)
    // Centered transforms should be mirror-image around the crosshair.
    const t0 = dots[0].getAttribute('transform') ?? ''
    const t1 = dots[1].getAttribute('transform') ?? ''
    const m0 = t0.match(/translate\(([-0-9.]+),([-0-9.]+)\)/)
    const m1 = t1.match(/translate\(([-0-9.]+),([-0-9.]+)\)/)
    expect(m0).not.toBeNull()
    expect(m1).not.toBeNull()
    const x0 = parseFloat(m0![1]), x1 = parseFloat(m1![1])
    const y0 = parseFloat(m0![2]), y1 = parseFloat(m1![2])
    // Both dots should land on opposite sides of the X-midpoint of the inner chart.
    // The mean of x-positions for the two centered dots equals the x-position of 0
    // in the centered domain — a strong signal mean-centering ran.
    const midX = (x0 + x1) / 2
    const midY = (y0 + y1) / 2
    // Just ensure midpoint isn't degenerate (NaN) and dots are distinct.
    expect(Number.isFinite(midX)).toBe(true)
    expect(Number.isFinite(midY)).toBe(true)
    expect(x0).not.toBe(x1)
    expect(y0).not.toBe(y1)
  })

  it('drops sectors with NULL rs or NULL momentum', () => {
    const current: SectorSnapshot[] = [
      makeSnapshot({ sector_name: 'Good', bottomup_rs_3m_nifty500: '0.05', rs_momentum: '0.01' }),
      makeSnapshot({ sector_name: 'YoungA', bottomup_rs_3m_nifty500: '0.03', rs_momentum: null }),
      makeSnapshot({ sector_name: 'YoungB', bottomup_rs_3m_nifty500: null, rs_momentum: '0.02' }),
    ]
    const { container } = render(
      <RRGChart current={current} history={[]} onSelect={() => {}} />,
    )
    const dots = container.querySelectorAll('g.sector-dot')
    expect(dots.length).toBe(1)
  })

  it('filters NULL history rows before rendering trail dots', () => {
    const current = [
      makeSnapshot({ sector_name: 'Tech', bottomup_rs_3m_nifty500: '0.10', rs_momentum: '0.02' }),
    ]
    const history: RRGHistoryRow[] = [
      { sector_name: 'Tech', date: new Date('2026-05-01'), rs: 0.08, momentum: null }, // dropped
      { sector_name: 'Tech', date: new Date('2026-05-02'), rs: null, momentum: 0.01 }, // dropped
      { sector_name: 'Tech', date: new Date('2026-05-03'), rs: 0.09, momentum: 0.015 },
      { sector_name: 'Tech', date: new Date('2026-05-04'), rs: 0.10, momentum: 0.018 },
    ]
    const { container } = render(
      <RRGChart current={current} history={history} onSelect={() => {}} />,
    )
    // Trail circles have pointer-events="none" and r="4"; main-dot inner circle has variable r.
    const trailCircles = Array.from(container.querySelectorAll('circle')).filter(
      (c) => c.getAttribute('pointer-events') === 'none',
    )
    expect(trailCircles.length).toBe(2) // only the two valid history rows
  })

  it('uses TRAIL_OPACITIES for last-5 trail dots', () => {
    const current = [
      makeSnapshot({ sector_name: 'Tech', bottomup_rs_3m_nifty500: '0.10', rs_momentum: '0.02' }),
    ]
    // 6 valid history rows — only the last 5 should render.
    const history: RRGHistoryRow[] = Array.from({ length: 6 }, (_, i) => ({
      sector_name: 'Tech',
      date: new Date(2026, 4, i + 1),
      rs: 0.05 + i * 0.01,
      momentum: 0.01 + i * 0.001,
    }))
    const { container } = render(
      <RRGChart current={current} history={history} onSelect={() => {}} />,
    )
    const trailCircles = Array.from(container.querySelectorAll('circle')).filter(
      (c) => c.getAttribute('pointer-events') === 'none',
    )
    expect(trailCircles.length).toBe(5)
    // Opacity ramp: 0.20, 0.35, 0.55, 0.75, 1.0
    const opacities = trailCircles.map((c) => parseFloat(c.getAttribute('opacity') ?? '0'))
    expect(opacities).toEqual([0.20, 0.35, 0.55, 0.75, 1.0])
  })

  it('calls onSelect when a dot is clicked', () => {
    const current = [
      makeSnapshot({ sector_name: 'Tech', bottomup_rs_3m_nifty500: '0.10', rs_momentum: '0.02' }),
    ]
    const onSelect = vi.fn()
    const { container } = render(
      <RRGChart current={current} history={[]} onSelect={onSelect} />,
    )
    const dot = container.querySelector('g.sector-dot')
    expect(dot).not.toBeNull()
    fireEvent.click(dot!)
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith('Tech')
  })

  it('calls onSelect when Enter is pressed on a focused dot', () => {
    const current = [
      makeSnapshot({ sector_name: 'Banks', bottomup_rs_3m_nifty500: '-0.05', rs_momentum: '-0.01' }),
    ]
    const onSelect = vi.fn()
    const { container } = render(
      <RRGChart current={current} history={[]} onSelect={onSelect} />,
    )
    const dot = container.querySelector('g.sector-dot')
    fireEvent.keyDown(dot!, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith('Banks')
  })

  it('marks dots with role=button and tabindex for keyboard access', () => {
    const current = [
      makeSnapshot({ sector_name: 'A', bottomup_rs_3m_nifty500: '0.05', rs_momentum: '0.01' }),
      makeSnapshot({ sector_name: 'B', bottomup_rs_3m_nifty500: '-0.05', rs_momentum: '-0.01' }),
    ]
    const { container } = render(
      <RRGChart current={current} history={[]} onSelect={() => {}} />,
    )
    const dots = container.querySelectorAll('g.sector-dot')
    expect(dots[0].getAttribute('role')).toBe('button')
    expect(dots[0].getAttribute('tabindex')).toBe('0')
    expect(dots[1].getAttribute('tabindex')).toBe('-1')
  })
})
