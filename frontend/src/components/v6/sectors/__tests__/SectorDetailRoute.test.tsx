// frontend/src/components/v6/sectors/__tests__/SectorDetailRoute.test.tsx
// Tests for detail-page components: ConstituentsTable, StrengthDistChart,
// OpenSignalsPanel, TopPicksPanel, RSWindowsTable.

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

// ── Module mocks (must be before imports that trigger module evaluation) ──────
// Mock the query module FIRST to prevent sectors.ts → db.ts → postgres from
// attempting a real Supabase connection during worker initialization.

vi.mock('@/lib/queries/v6/sectors', () => ({}))
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

// ── next/link mock ────────────────────────────────────────────────────────────

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

// ── Recharts mock ─────────────────────────────────────────────────────────────

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="rc">{children}</div>
  ),
  BarChart: ({ children }: { children: ReactNode }) => (
    <svg data-testid="bar-chart">{children}</svg>
  ),
  Bar: ({ children }: { children: ReactNode }) => (
    <g data-testid="bar">{children}</g>
  ),
  Cell: ({ fill }: { fill?: string }) => <rect fill={fill} />,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ReferenceLine: () => null,
  Label: ({ value }: { value: string }) => <text>{value}</text>,
}))

// ── Imports AFTER mock ────────────────────────────────────────────────────────

import { ConstituentsTable } from '../ConstituentsTable'
import { StrengthDistChart } from '../StrengthDistChart'
import { OpenSignalsPanel } from '../OpenSignalsPanel'
import { TopPicksPanel } from '../TopPicksPanel'
import type { ConstituentRow, OpenSignalRow, TopPickRow, StrengthDist } from '@/lib/queries/v6/sectors'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeConstituent(overrides: Partial<ConstituentRow> = {}): ConstituentRow {
  return {
    symbol: 'RELIANCE',
    company_name: 'Reliance Industries',
    tier: 'Large',
    ret_1w: 1.8,
    ret_1m: 6.8,
    ret_3m: 14.2,
    ret_6m: 21.0,
    rs_3m_nifty500_pp: 8.4,
    vol_60d: 14.2,
    rs_state: 'Leader',
    composite_score: 5.8,
    confidence_band: 'H',
    action: 'POSITIVE',
    ...overrides,
  }
}

function makeSignal(overrides: Partial<OpenSignalRow> = {}): OpenSignalRow {
  return {
    symbol: 'RELIANCE',
    company_name: 'Reliance Industries',
    action: 'POSITIVE',
    tenure: 'Medium',
    cap_tier_at_trigger: 'Large',
    confidence_unconditional: 0.82,
    signal_date: '2026-04-15',
    ...overrides,
  }
}

function makePick(overrides: Partial<TopPickRow> = {}): TopPickRow {
  return {
    symbol: 'RELIANCE',
    company_name: 'Reliance Industries',
    composite_score: 5.8,
    confidence_band: 'H',
    action: 'POSITIVE',
    ...overrides,
  }
}

function makeDist(overrides: Partial<StrengthDist> = {}): StrengthDist {
  return {
    very_strong: 12,
    strong: 14,
    neutral: 16,
    weak: 12,
    very_weak: 8,
    ...overrides,
  }
}

// ── ConstituentsTable ─────────────────────────────────────────────────────────

describe('ConstituentsTable', () => {
  it('renders empty state', () => {
    render(<ConstituentsTable constituents={[]} />)
    expect(screen.getByText(/No constituent data available/i)).toBeTruthy()
  })

  it('renders a row per constituent', () => {
    const rows = [
      makeConstituent({ symbol: 'RELIANCE', composite_score: 5.8 }),
      makeConstituent({ symbol: 'ONGC',     composite_score: 3.2 }),
    ]
    render(<ConstituentsTable constituents={rows} />)
    expect(screen.getByTestId('constituent-row-RELIANCE')).toBeTruthy()
    expect(screen.getByTestId('constituent-row-ONGC')).toBeTruthy()
  })

  it('renders formatted return values (already percentages from MV)', () => {
    render(<ConstituentsTable constituents={[makeConstituent({ ret_1m: 6.8, ret_3m: 14.2 })]} />)
    expect(screen.getByText('+6.8%')).toBeTruthy()
    expect(screen.getByText('+14.2%')).toBeTruthy()
  })

  it('renders null returns as em-dash', () => {
    render(<ConstituentsTable constituents={[makeConstituent({ ret_1m: null })]} />)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('renders negative composite score with minus sign', () => {
    render(<ConstituentsTable constituents={[makeConstituent({ composite_score: -2.5 })]} />)
    expect(screen.getByText('-2.5')).toBeTruthy()
  })

  it('renders table with correct testid', () => {
    render(<ConstituentsTable constituents={[makeConstituent()]} />)
    expect(screen.getByTestId('constituents-table')).toBeTruthy()
  })
})

// ── StrengthDistChart ─────────────────────────────────────────────────────────

describe('StrengthDistChart', () => {
  it('renders empty state when all zeros', () => {
    render(<StrengthDistChart dist={{ very_strong: 0, strong: 0, neutral: 0, weak: 0, very_weak: 0 }} />)
    expect(screen.getByText(/unavailable/i)).toBeTruthy()
  })

  it('renders chart when data exists', () => {
    render(<StrengthDistChart dist={makeDist()} />)
    expect(screen.getByTestId('strength-dist-chart')).toBeTruthy()
  })

  it('renders bar chart element', () => {
    render(<StrengthDistChart dist={makeDist()} />)
    expect(screen.getByTestId('bar-chart')).toBeTruthy()
  })
})

// ── OpenSignalsPanel ──────────────────────────────────────────────────────────

describe('OpenSignalsPanel', () => {
  it('renders empty state', () => {
    render(<OpenSignalsPanel signals={[]} />)
    expect(screen.getByTestId('open-signals-empty')).toBeTruthy()
    expect(screen.getByText(/No open signals/i)).toBeTruthy()
  })

  it('renders signal panel when signals exist', () => {
    render(<OpenSignalsPanel signals={[makeSignal({ symbol: 'RELIANCE' })]} />)
    expect(screen.getByTestId('open-signals-panel')).toBeTruthy()
    expect(screen.getByText('RELIANCE')).toBeTruthy()
  })

  it('renders BUY label for POSITIVE action', () => {
    render(<OpenSignalsPanel signals={[makeSignal({ action: 'POSITIVE' })]} />)
    expect(screen.getByText('BUY')).toBeTruthy()
  })

  it('renders SELL label for NEGATIVE action', () => {
    render(<OpenSignalsPanel signals={[makeSignal({ action: 'NEGATIVE' })]} />)
    expect(screen.getByText('SELL')).toBeTruthy()
  })

  it('renders confidence as percentage', () => {
    render(<OpenSignalsPanel signals={[makeSignal({ confidence_unconditional: 0.82 })]} />)
    expect(screen.getByText('82%')).toBeTruthy()
  })
})

// ── TopPicksPanel ─────────────────────────────────────────────────────────────

describe('TopPicksPanel', () => {
  it('renders empty state when no picks', () => {
    render(<TopPicksPanel picks={[]} />)
    expect(screen.getByText(/No top picks/i)).toBeTruthy()
  })

  it('renders pick rows', () => {
    render(<TopPicksPanel picks={[makePick({ symbol: 'RELIANCE', composite_score: 5.8 })]} />)
    expect(screen.getByTestId('top-picks-panel')).toBeTruthy()
    expect(screen.getByTestId('top-pick-RELIANCE')).toBeTruthy()
  })

  it('renders composite score with sign', () => {
    render(<TopPicksPanel picks={[makePick({ composite_score: 5.8 })]} />)
    expect(screen.getByText('+5.8')).toBeTruthy()
  })

  it('renders rank numbers starting at 1', () => {
    const picks = [
      makePick({ symbol: 'RELIANCE', composite_score: 5.8 }),
      makePick({ symbol: 'ONGC',     composite_score: 3.2 }),
    ]
    render(<TopPicksPanel picks={picks} />)
    expect(screen.getByText('1')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy()
  })
})
