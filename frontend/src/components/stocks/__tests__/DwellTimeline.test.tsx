import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { DwellTimeline } from '../DwellTimeline'
import type { StateHistoryEntry } from '@/lib/queries/states'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeEntry(i: number, state: string): StateHistoryEntry {
  return {
    date:       `2026-01-${String(i + 1).padStart(2, '0')}`,
    state,
    dwell_days: i + 1,
  }
}

function makeHistory(n: number, state = 'stage_2c'): StateHistoryEntry[] {
  // getStateHistory returns most-recent-first
  return Array.from({ length: n }, (_, i) => makeEntry(n - 1 - i, state)).reverse()
}

// ---------------------------------------------------------------------------
// Test 1: renders correct number of bars
// ---------------------------------------------------------------------------

describe('DwellTimeline — bar count', () => {
  it('renders exactly 50 bars for a 50-entry history', () => {
    render(<DwellTimeline history={makeHistory(50)} />)
    const bars = screen.getByTestId('dwell-bars')
    // Each bar is a direct child div
    expect(bars.children).toHaveLength(50)
  })

  it('renders exactly 252 bars for a 252-entry history', () => {
    render(<DwellTimeline history={makeHistory(252)} />)
    const bars = screen.getByTestId('dwell-bars')
    expect(bars.children).toHaveLength(252)
  })

  it('renders the section heading', () => {
    render(<DwellTimeline history={makeHistory(50)} />)
    expect(screen.getByTestId('dwell-timeline')).toBeInTheDocument()
    expect(screen.getByText(/State history/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: color mapping for stage_2c
// ---------------------------------------------------------------------------

describe('DwellTimeline — color mapping', () => {
  it('applies bg-signal-warn class to stage_2c bars', () => {
    render(<DwellTimeline history={makeHistory(30, 'stage_2c')} />)
    const bars = screen.getByTestId('dwell-bars')
    const firstBar = bars.children[0] as HTMLElement
    expect(firstBar.className).toContain('bg-signal-warn')
  })

  it('applies bg-signal-pos class to stage_2a bars', () => {
    render(<DwellTimeline history={makeHistory(30, 'stage_2a')} />)
    const bars = screen.getByTestId('dwell-bars')
    const firstBar = bars.children[0] as HTMLElement
    expect(firstBar.className).toContain('bg-signal-pos')
  })

  it('applies bg-signal-neg class to stage_4 bars', () => {
    render(<DwellTimeline history={makeHistory(30, 'stage_4')} />)
    const bars = screen.getByTestId('dwell-bars')
    const firstBar = bars.children[0] as HTMLElement
    expect(firstBar.className).toContain('bg-signal-neg')
  })

  it('renders the legend only for states present in history', () => {
    render(<DwellTimeline history={makeHistory(30, 'stage_2c')} />)
    // stage_2c is present → its legend entry should render
    expect(screen.getByText('Stage 2C')).toBeInTheDocument()
    // stage_4 is not present → should not render
    expect(screen.queryByText('Stage 4')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 3: insufficient history placeholder
// ---------------------------------------------------------------------------

describe('DwellTimeline — insufficient history', () => {
  it('renders placeholder when history has fewer than 30 entries', () => {
    render(<DwellTimeline history={makeHistory(10)} />)
    expect(screen.getByText(/Insufficient history/i)).toBeInTheDocument()
  })

  it('does not render bars when history is too short', () => {
    render(<DwellTimeline history={makeHistory(10)} />)
    expect(screen.queryByTestId('dwell-bars')).not.toBeInTheDocument()
  })
})
