/**
 * Tests for C1 (signal-components state mapping) and C2 (RS participation suppression).
 *
 * C1: SectorDrawerSnapshot must render real state values when the snapshot has
 *     bottomup_state / topdown_state / bottomup_rs_state / bottomup_momentum_state
 *     populated — not show "—" dashes for every cell.
 *
 * C2: SectorOverviewTab must render the honest placeholder message instead of the
 *     broken RS Participation chart whose upstream data is near-zero garbage.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SectorDrawerSnapshot } from '../SectorDrawerSnapshot'
import { SectorOverviewTab } from '../SectorOverviewTab'
import type { SectorDecision } from '@/lib/sectors-decision'
import type { SectorSnapshot } from '@/lib/queries/sectors'
import type { SectorBriefSnapshot } from '@/lib/queries/sector-deep-dive'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSnapshot(over: Partial<SectorSnapshot> = {}): SectorSnapshot & { decision: SectorDecision } {
  return {
    sector_name: 'Banking',
    constituent_count: 34,
    bottomup_ret_1w: '0.01',
    bottomup_ret_1m: '-0.02',
    bottomup_ret_3m: '-0.05',
    bottomup_ret_6m: '-0.10',
    bottomup_rs_3m_nifty500: '-0.08',
    rs_momentum: '-0.02',
    bottomup_ema_10_ratio: '0.98',
    bottomup_ema_20_ratio: '0.97',
    topdown_ret_1m: null,
    topdown_ret_3m: null,
    topdown_rs_3m_nifty500: null,
    topdown_index_code: null,
    participation_50: '0.35',
    participation_rs: '0.03',
    participation_rs_pct: '0.03',
    leadership_concentration: '0.45',
    sector_state: 'Underweight',
    bottomup_state: 'Underweight',
    topdown_state: 'Avoid',
    divergence_flag: true,
    bottomup_rs_state: 'Avoid_RS',
    bottomup_momentum_state: 'Deteriorating',
    bottomup_risk_state: null,
    bottomup_volume_state: null,
    data_date: new Date('2026-05-19'),
    pct_stage_2: null,
    pct_stage_3: null,
    pct_stage_4: null,
    mean_within_state_rank: null,
    decision: 'PASS',
    ...over,
  }
}

function makeBriefSnapshot(over: Partial<SectorBriefSnapshot> = {}): SectorBriefSnapshot & { decision: SectorDecision } {
  const base = makeSnapshot()
  return { ...base, ...over, decision: 'PASS' }
}

// ---------------------------------------------------------------------------
// C1: SectorDrawerSnapshot — signal components render real values
// ---------------------------------------------------------------------------

describe('SectorDrawerSnapshot — C1 signal components', () => {
  it('renders bottomup_state value when populated (not em-dash)', () => {
    render(<SectorDrawerSnapshot snapshot={makeSnapshot()} />)
    // "Underweight" should appear in the Bottom-up badge
    const badges = screen.getAllByText('Underweight')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('renders topdown_state "Avoid" when populated', () => {
    render(<SectorDrawerSnapshot snapshot={makeSnapshot()} />)
    // 'Avoid' appears in the top-down badge and possibly the divergence callout
    const avoids = screen.getAllByText('Avoid')
    expect(avoids.length).toBeGreaterThan(0)
  })

  it('renders bottomup_momentum_state chip when populated', () => {
    render(<SectorDrawerSnapshot snapshot={makeSnapshot()} />)
    // MomentumChip maps 'Deteriorating' -> abbreviated label 'Det'; the raw value
    // appears as the title attribute on the chip span.
    // Check by title attribute so we're robust to label abbreviation changes.
    const el = document.querySelector('[title="Deteriorating"]')
    expect(el).not.toBeNull()
  })

  it('renders bottomup_rs_state chip when populated', () => {
    render(<SectorDrawerSnapshot snapshot={makeSnapshot()} />)
    // RSStateChip: 'Avoid_RS' is not in RS_STATE_LABEL so falls back to the raw value
    // as the visible label text AND as the title attribute.
    const el = screen.queryByText('Avoid_RS')
    expect(el).not.toBeNull()
  })

  it('shows em-dash for bottomup_risk_state when null (not computed at sector level)', () => {
    render(<SectorDrawerSnapshot snapshot={makeSnapshot({ bottomup_risk_state: null })} />)
    // RiskChip renders '—' when value is null — check the Risk label box exists
    const riskLabel = screen.getByText('Risk', { exact: false })
    expect(riskLabel).toBeDefined()
    // At least one em-dash should be present (risk + volume both null)
    const emdashes = screen.getAllByText('—')
    expect(emdashes.length).toBeGreaterThan(0)
  })

  it('renders divergence callout when divergence_flag is true', () => {
    render(<SectorDrawerSnapshot snapshot={makeSnapshot({ divergence_flag: true })} />)
    expect(screen.getByText(/Signal Divergence/i)).toBeDefined()
  })

  it('does NOT render divergence callout when divergence_flag is false', () => {
    render(<SectorDrawerSnapshot snapshot={makeSnapshot({ divergence_flag: false })} />)
    expect(screen.queryByText(/Signal Divergence/i)).toBeNull()
  })

  it('shows em-dash for all state chips when all states are null', () => {
    render(
      <SectorDrawerSnapshot
        snapshot={makeSnapshot({
          bottomup_state: null,
          topdown_state: null,
          bottomup_rs_state: null,
          bottomup_momentum_state: null,
          bottomup_risk_state: null,
          bottomup_volume_state: null,
        })}
      />,
    )
    // All 6 chips should render '—' — at least 4 should be present
    const emdashes = screen.getAllByText('—')
    expect(emdashes.length).toBeGreaterThanOrEqual(4)
  })
})

// ---------------------------------------------------------------------------
// C2: SectorOverviewTab — RS Participation chart suppressed
// ---------------------------------------------------------------------------

describe('SectorOverviewTab — C2 RS participation suppression', () => {
  const emptyMetricHistory = [
    {
      date: new Date('2026-05-19'),
      bottomup_rs_3m_nifty500: '-0.08',
      topdown_rs_3m_nifty500: null,
      topdown_ret_1m: null,
      topdown_ret_3m: null,
      participation_50: '0.35',
      participation_rs: '0.03',
      participation_rs_pct: '0.03',
      leadership_concentration: null,
      bottomup_ret_3m: '-0.05',
      bottomup_ema_10_ratio: '0.98',
      bottomup_ema_20_ratio: '0.97',
      sector_state: 'Underweight',
    },
  ]

  it('renders the "temporarily unavailable" placeholder instead of an RS Participation chart', () => {
    render(
      <SectorOverviewTab
        snapshot={makeBriefSnapshot()}
        metricHistory={emptyMetricHistory}
        stateHistory={[]}
        range="3M"
        regime={null}
        breadthData={[]}
      />,
    )
    expect(
      screen.getByText(/RS participation metric under data-quality review/i),
    ).toBeDefined()
  })

  it('does NOT render the "RS PARTICIPATION" chart area with actual chart data', () => {
    render(
      <SectorOverviewTab
        snapshot={makeBriefSnapshot()}
        metricHistory={emptyMetricHistory}
        stateHistory={[]}
        range="3M"
        regime={null}
        breadthData={[]}
      />,
    )
    // The IndicatorChart for RS participation should NOT be rendered.
    // Its description text should be absent.
    expect(
      screen.queryByText(/Fraction of the sector.*stocks outperforming Nifty 500/i),
    ).toBeNull()
  })

  it('still renders the Breadth chart (participation_50) alongside the suppressed RS chart', () => {
    render(
      <SectorOverviewTab
        snapshot={makeBriefSnapshot()}
        metricHistory={emptyMetricHistory}
        stateHistory={[]}
        range="3M"
        regime={null}
        breadthData={[]}
      />,
    )
    // Breadth chart title should still be present
    expect(screen.getByText(/Breadth.*Stocks Above 50-Day EMA/i)).toBeDefined()
  })
})
