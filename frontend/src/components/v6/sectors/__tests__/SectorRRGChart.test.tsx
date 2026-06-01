// frontend/src/components/v6/sectors/__tests__/SectorRRGChart.test.tsx
// Tests for SectorRRGChart component.
//
// Coverage:
//   - Empty state when no valid rs_ratio/rs_momentum data
//   - Quadrant legend renders all 4 quadrant names
//   - Dots render with correct testid and aria-label
//   - Trail data passes through without error

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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

// ── Recharts mock — avoid heavy chart rendering in tests ──────────────────────

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="rc">{children}</div>
  ),
  ScatterChart: ({ children }: { children: ReactNode }) => (
    <svg data-testid="scatter-chart">{children}</svg>
  ),
  Scatter: ({ data, shape }: { data: unknown[]; shape: (p: unknown) => ReactNode }) => (
    <g data-testid="scatter">
      {Array.isArray(data) && data.map((d, i) => {
        const rendered = typeof shape === 'function' ? shape({ cx: 100 + i * 10, cy: 100 + i * 10, payload: d }) : null
        return <g key={i}>{rendered}</g>
      })}
    </g>
  ),
  XAxis: ({ children }: { children?: ReactNode }) => <g data-testid="xaxis">{children}</g>,
  YAxis: ({ children }: { children?: ReactNode }) => <g data-testid="yaxis">{children}</g>,
  CartesianGrid: () => null,
  ReferenceLine: () => null,
  Tooltip: () => null,
  Label: ({ value }: { value: string }) => <text>{value}</text>,
}))

// ── Import AFTER mock ─────────────────────────────────────────────────────────

import { SectorRRGChart } from '../SectorRRGChart'
import type { SectorRRGRow } from '@/lib/queries/v6/sectors'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeRRGRow(overrides: Partial<SectorRRGRow> = {}): SectorRRGRow {
  return {
    as_of_date: '2026-05-27',
    sector_name: 'Energy',
    rs_ratio_current: 105.2,
    rs_momentum_current: 2.4,
    quadrant_current: 'Leading',
    trail_6w: [],
    constituent_count: 62,
    ...overrides,
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SectorRRGChart', () => {
  it('renders empty state when all rows have null rs_ratio', () => {
    const data: SectorRRGRow[] = [
      makeRRGRow({ rs_ratio_current: null, rs_momentum_current: null }),
    ]
    render(<SectorRRGChart data={data} />)
    expect(screen.getByText(/RRG data unavailable/i)).toBeTruthy()
  })

  it('renders chart container with valid data', () => {
    const data: SectorRRGRow[] = [
      makeRRGRow({ sector_name: 'Energy', rs_ratio_current: 105, rs_momentum_current: 2, quadrant_current: 'Leading' }),
    ]
    render(<SectorRRGChart data={data} />)
    expect(screen.getByTestId('scatter-chart')).toBeTruthy()
  })

  it('renders a dot for a valid sector', () => {
    const data: SectorRRGRow[] = [
      makeRRGRow({ sector_name: 'Energy', rs_ratio_current: 105, rs_momentum_current: 2, quadrant_current: 'Leading' }),
    ]
    render(<SectorRRGChart data={data} />)
    expect(screen.getByTestId('rrg-dot-Energy')).toBeTruthy()
  })

  it('assigns correct aria-label containing quadrant', () => {
    const data: SectorRRGRow[] = [
      makeRRGRow({ sector_name: 'Energy', rs_ratio_current: 105, rs_momentum_current: 2, quadrant_current: 'Leading' }),
    ]
    render(<SectorRRGChart data={data} />)
    const dot = screen.getByTestId('rrg-dot-Energy')
    expect(dot.getAttribute('aria-label')).toContain('Leading')
  })

  it('renders quadrant legend with all 4 quadrant names', () => {
    const data: SectorRRGRow[] = [
      makeRRGRow({ sector_name: 'Energy', rs_ratio_current: 105, rs_momentum_current: 2, quadrant_current: 'Leading' }),
    ]
    render(<SectorRRGChart data={data} />)
    // Legend block always renders all 4 quadrant names
    expect(screen.getAllByText(/Leading/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Weakening/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Improving/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Lagging/).length).toBeGreaterThan(0)
  })

  it('renders dots for all 4 quadrant types without error', () => {
    const data: SectorRRGRow[] = [
      makeRRGRow({ sector_name: 'Energy',   rs_ratio_current: 105, rs_momentum_current: 2,  quadrant_current: 'Leading' }),
      makeRRGRow({ sector_name: 'IT',       rs_ratio_current: 102, rs_momentum_current: -1, quadrant_current: 'Weakening' }),
      makeRRGRow({ sector_name: 'Metals',   rs_ratio_current: 96,  rs_momentum_current: -2, quadrant_current: 'Lagging' }),
      makeRRGRow({ sector_name: 'Auto',     rs_ratio_current: 98,  rs_momentum_current: 1,  quadrant_current: 'Improving' }),
    ]
    expect(() => render(<SectorRRGChart data={data} />)).not.toThrow()
    expect(screen.getByTestId('rrg-dot-Energy')).toBeTruthy()
    expect(screen.getByTestId('rrg-dot-IT')).toBeTruthy()
    expect(screen.getByTestId('rrg-dot-Metals')).toBeTruthy()
    expect(screen.getByTestId('rrg-dot-Auto')).toBeTruthy()
  })

  it('passes trail data without error', () => {
    const data: SectorRRGRow[] = [
      makeRRGRow({
        trail_6w: [
          { week_end_date: '2026-05-20', rs_ratio: 104, rs_momentum: 1.8, quadrant: 'Leading' },
          { week_end_date: '2026-05-13', rs_ratio: 103, rs_momentum: 1.2, quadrant: 'Leading' },
        ],
      }),
    ]
    expect(() => render(<SectorRRGChart data={data} />)).not.toThrow()
  })
})
