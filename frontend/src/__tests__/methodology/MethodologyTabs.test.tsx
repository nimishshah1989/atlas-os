// Tests for src/components/methodology/MethodologyTabs.tsx
// Verifies the v2 decision engine content is present in the overview and sectors tabs.

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MethodologyTabs } from '@/components/methodology/MethodologyTabs'

const NO_ACTIVE_SETS: { tier: string; predicted_ic: string | null }[] = []

const WITH_ACTIVE_SETS = [
  { tier: 'tier_1_megacap', predicted_ic: '0.0520' },
  { tier: 'tier_2_largecap', predicted_ic: '0.0310' },
]

describe('MethodologyTabs — overview tab (default)', () => {
  it('renders the v2 decision engine heading', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText(/v2 decision engine/i)).toBeTruthy()
  })

  it('renders the layered targets section', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText(/layered targets/i)).toBeTruthy()
  })

  it('renders the policy rails section heading', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText(/policy rails/i)).toBeTruthy()
  })

  it('renders the recommendation formula', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText(/engine_signal ∩ policy_constraint/)).toBeTruthy()
  })

  it('renders the 6-step decision flow section', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText(/6-step decision flow/i)).toBeTruthy()
  })

  it('renders all six step labels', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText(/Step 1 — Regime/)).toBeTruthy()
    expect(screen.getByText(/Step 2 — Sector rotation/)).toBeTruthy()
    expect(screen.getByText(/Step 3 — Fill the target/)).toBeTruthy()
    expect(screen.getByText(/Step 4 — Conviction check/)).toBeTruthy()
    expect(screen.getByText(/Step 5 — Act/)).toBeTruthy()
    expect(screen.getByText(/Step 6 — Deterioration loop/)).toBeTruthy()
  })

  it('renders the 4-signal scorecard section', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText(/4-signal bottom-up scorecard/i)).toBeTruthy()
  })

  it('renders all four scorecard signal names', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText('Trend')).toBeTruthy()
    expect(screen.getByText('Breadth')).toBeTruthy()
    expect(screen.getByText('Momentum')).toBeTruthy()
    expect(screen.getByText('Participation')).toBeTruthy()
  })

  it('renders the Weinstein state engine card in the pillars grid', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByText(/Weinstein State Engine/i)).toBeTruthy()
  })
})

describe('MethodologyTabs — sectors tab', () => {
  function renderSectorsTab() {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    // The button label is "Sectors & RRG"
    const sectorsBtn = screen.getByRole('button', { name: 'Sectors & RRG' })
    fireEvent.click(sectorsBtn)
  }

  it('renders the hybrid classifier section heading', () => {
    renderSectorsTab()
    expect(screen.getByText(/hybrid rank \+ absolute floor — the sector classifier/i)).toBeTruthy()
  })

  it('renders the daily cross-sectional rank sub-heading', () => {
    renderSectorsTab()
    expect(screen.getByText(/part 1 — daily cross-sectional rank/i)).toBeTruthy()
  })

  it('renders the absolute floor sub-heading', () => {
    renderSectorsTab()
    expect(screen.getByText(/part 2 — absolute floor/i)).toBeTruthy()
  })

  it('renders all four sector label bands', () => {
    renderSectorsTab()
    expect(screen.getAllByText('Overweight').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Neutral').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Underweight').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Avoid').length).toBeGreaterThanOrEqual(1)
  })

  it('renders the Weinstein stage breadth section', () => {
    renderSectorsTab()
    expect(screen.getByText(/Weinstein stage breadth — the bottom-up truth/i)).toBeTruthy()
  })

  it('renders pct_stage_2 metric references', () => {
    renderSectorsTab()
    // pct_stage_2 appears multiple times (sub-headings and table); getAllByText is correct
    const matches = screen.getAllByText(/pct_stage_2/)
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })

  it('renders the fund classifier section', () => {
    renderSectorsTab()
    expect(screen.getByText(/fund classifier — the same hybrid model/i)).toBeTruthy()
  })
})

describe('MethodologyTabs — conviction tab with active weight sets', () => {
  it('renders live tier IC data when active sets are provided', () => {
    render(<MethodologyTabs activeSets={WITH_ACTIVE_SETS} />)
    // The button label is "Conviction & IC"
    const convBtn = screen.getByRole('button', { name: 'Conviction & IC' })
    fireEvent.click(convBtn)
    expect(screen.getByText(/T1 · Mega-cap/)).toBeTruthy()
    expect(screen.getByText(/T2 · Large-cap/)).toBeTruthy()
  })
})

describe('MethodologyTabs — tab navigation', () => {
  it('all six tab buttons are present', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Stock States' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Market Regime' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Sectors & RRG' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Conviction & IC' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Admin Guide' })).toBeTruthy()
  })

  it('switching to Stock States tab renders RS State content', () => {
    render(<MethodologyTabs activeSets={NO_ACTIVE_SETS} />)
    fireEvent.click(screen.getByRole('button', { name: 'Stock States' }))
    expect(screen.getByText(/RS State — relative strength rank/i)).toBeTruthy()
  })
})
