// frontend/src/components/v6/__tests__/SectorBreadthPanel.test.tsx
//
// Tests for SectorBreadthPanel component.
//
// Tightened acceptance criteria (per Opus review):
//   - 3 concentration badge fixtures (top3=0.35, 0.55, 0.72 as decimal fractions
//     stored as pp strings: "35.00", "55.00", "72.00")
//   - Badge DOM node has class `signal-pos` / `signal-warn` / `signal-neg`
//   - Badge text content = "Broad participation" / "Distributed" / "Narrow leadership ⚠" (verbatim)
//   - KPI tiles (gauge bars) render with formatted pct
//   - ARIA labels present

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SectorBreadthPanel } from '../SectorBreadthPanel'
import type { SectorBreadth } from '@/lib/queries/v6/sector_breadth'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeBreadth(overrides: Partial<SectorBreadth> = {}): SectorBreadth {
  return {
    sector: 'Banking',
    n_stocks: 38,
    pct_above_sma20: '74.00',
    pct_above_sma50: '66.00',
    pct_above_sma200: '58.00',
    top3_concentration_pct: '35.00',
    dispersion_sigma: '18.00',
    as_of_date: '2026-05-26',
    ...overrides,
  }
}

// top3_concentration_pct fixtures (in pp string form: "35.00" = 35%)
const BROAD_FIXTURE = makeBreadth({ top3_concentration_pct: '35.00' })         // < 40%
const DISTRIBUTED_FIXTURE = makeBreadth({ top3_concentration_pct: '55.00' })   // 40–65%
const NARROW_FIXTURE = makeBreadth({ top3_concentration_pct: '72.00' })        // > 65%

// ---------------------------------------------------------------------------
// Block 1: Concentration badge — class AND text (Opus tightened)
// ---------------------------------------------------------------------------

describe('SectorBreadthPanel — concentration badge (tightened per Opus)', () => {
  it('top3=35% → badge has class signal-pos and text "Broad participation"', () => {
    const { container } = render(<SectorBreadthPanel breadth={BROAD_FIXTURE} />)
    const badge = container.querySelector('.signal-pos')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toBe('Broad participation')
  })

  it('top3=55% → badge has class signal-warn and text "Distributed"', () => {
    const { container } = render(<SectorBreadthPanel breadth={DISTRIBUTED_FIXTURE} />)
    const badge = container.querySelector('.signal-warn')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toBe('Distributed')
  })

  it('top3=72% → badge has class signal-neg and text "Narrow leadership ⚠"', () => {
    const { container } = render(<SectorBreadthPanel breadth={NARROW_FIXTURE} />)
    const badge = container.querySelector('.signal-neg')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toBe('Narrow leadership ⚠')
  })

  it('badge is mutually exclusive — broad fixture has no signal-warn or signal-neg badge class', () => {
    const { container } = render(<SectorBreadthPanel breadth={BROAD_FIXTURE} />)
    // signal-warn / signal-neg should NOT appear as badge class on concentration badge
    // (they may exist elsewhere but the badge element specifically must be signal-pos)
    const badge = container.querySelector('.signal-pos')
    expect(badge).not.toBeNull()
    expect(badge!.classList.contains('signal-warn')).toBe(false)
    expect(badge!.classList.contains('signal-neg')).toBe(false)
  })

  it('boundary: top3=40% → "Distributed" (40–65 inclusive lower)', () => {
    const { container } = render(
      <SectorBreadthPanel breadth={makeBreadth({ top3_concentration_pct: '40.00' })} />
    )
    const badge = container.querySelector('.signal-warn')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toBe('Distributed')
  })

  it('boundary: top3=65% → "Distributed" (40–65 inclusive upper)', () => {
    const { container } = render(
      <SectorBreadthPanel breadth={makeBreadth({ top3_concentration_pct: '65.00' })} />
    )
    const badge = container.querySelector('.signal-warn')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toBe('Distributed')
  })

  it('boundary: top3=65.01% → "Narrow leadership ⚠"', () => {
    const { container } = render(
      <SectorBreadthPanel breadth={makeBreadth({ top3_concentration_pct: '65.01' })} />
    )
    const badge = container.querySelector('.signal-neg')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toBe('Narrow leadership ⚠')
  })
})

// ---------------------------------------------------------------------------
// Block 2: KPI tiles (gauge bars) render with formatted pct
// ---------------------------------------------------------------------------

describe('SectorBreadthPanel — KPI gauge bars', () => {
  it('renders Above EMA20 gauge with formatted percentage', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ pct_above_sma20: '74.00' })} />)
    // gauge bar label
    expect(screen.getByText('Above EMA20')).toBeInTheDocument()
    // formatted pct text: "74.00" → "74.0%"
    expect(screen.getByText('74.0%')).toBeInTheDocument()
  })

  it('renders Above EMA50 gauge with formatted percentage', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ pct_above_sma50: '66.00' })} />)
    expect(screen.getByText('Above EMA50')).toBeInTheDocument()
    expect(screen.getByText('66.0%')).toBeInTheDocument()
  })

  it('renders Above EMA200 gauge with formatted percentage', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ pct_above_sma200: '58.00' })} />)
    expect(screen.getByText('Above EMA200')).toBeInTheDocument()
    expect(screen.getByText('58.0%')).toBeInTheDocument()
  })

  it('renders sector name in header', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ sector: 'Capital Goods' })} />)
    expect(screen.getByText('Capital Goods')).toBeInTheDocument()
  })

  it('renders as_of_date in header', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ as_of_date: '2026-05-26' })} />)
    expect(screen.getByText('2026-05-26')).toBeInTheDocument()
  })

  it('renders constituent count', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ n_stocks: 38 })} />)
    expect(screen.getByText(/38 constituents/)).toBeInTheDocument()
  })

  it('renders dispersion sigma readout', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ dispersion_sigma: '18.00' })} />)
    expect(screen.getByText('18.0%')).toBeInTheDocument()
    expect(screen.getByText('moderate')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Block 3: Dispersion sigma qualitative labels
// ---------------------------------------------------------------------------

describe('SectorBreadthPanel — dispersion labels', () => {
  it('σ < 10pp → "consensus"', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ dispersion_sigma: '7.50' })} />)
    expect(screen.getByText('consensus')).toBeInTheDocument()
  })

  it('σ = 15pp → "moderate"', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ dispersion_sigma: '15.00' })} />)
    expect(screen.getByText('moderate')).toBeInTheDocument()
  })

  it("σ > 20pp → \"stockpicker's\"", () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ dispersion_sigma: '25.00' })} />)
    expect(screen.getByText("stockpicker's")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Block 4: ARIA labels
// ---------------------------------------------------------------------------

describe('SectorBreadthPanel — ARIA labels', () => {
  it('section has aria-label with sector name', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ sector: 'IT' })} />)
    expect(
      screen.getByRole('region', { name: /Sector breadth panel for IT/ }),
    ).toBeInTheDocument()
  })

  it('gauge bars have aria-label with pct and label', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ pct_above_sma20: '74.00' })} />)
    expect(
      screen.getByLabelText(/Above EMA20: 74\.0% of constituents above/),
    ).toBeInTheDocument()
  })

  it('dispersion row has aria-label', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ dispersion_sigma: '18.00' })} />)
    expect(
      screen.getByLabelText(/Sector dispersion sigma/),
    ).toBeInTheDocument()
  })

  it('concentration badge has aria-label', () => {
    render(<SectorBreadthPanel breadth={BROAD_FIXTURE} />)
    expect(
      screen.getByLabelText(/Concentration: Broad participation/),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Block 5: Missing / edge-case data
// ---------------------------------------------------------------------------

describe('SectorBreadthPanel — missing data edge cases', () => {
  it('handles zero n_stocks gracefully', () => {
    render(<SectorBreadthPanel breadth={makeBreadth({ n_stocks: 0 })} />)
    expect(screen.getByText(/0 constituents/)).toBeInTheDocument()
  })

  it('handles "0.00" top3_concentration → Broad participation', () => {
    const { container } = render(
      <SectorBreadthPanel breadth={makeBreadth({ top3_concentration_pct: '0.00' })} />
    )
    const badge = container.querySelector('.signal-pos')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toBe('Broad participation')
  })

  it('clamps gauge bar to 0% width for "0.00" pct', () => {
    const { container } = render(
      <SectorBreadthPanel breadth={makeBreadth({ pct_above_sma200: '0.00' })} />
    )
    // The inner fill span should have width: 0%
    const fillSpans = container.querySelectorAll('[style*="width: 0%"]')
    expect(fillSpans.length).toBeGreaterThan(0)
  })

  it('accepts custom className on root section', () => {
    const { container } = render(
      <SectorBreadthPanel breadth={makeBreadth()} className="my-custom-class" />
    )
    expect(container.firstElementChild?.classList.contains('my-custom-class')).toBe(true)
  })
})
