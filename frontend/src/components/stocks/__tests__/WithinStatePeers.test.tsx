import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { WithinStatePeers } from '../WithinStatePeers'
import type { WithinStatePeer } from '@/lib/queries/states'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePeer(overrides: Partial<WithinStatePeer> = {}): WithinStatePeer {
  return {
    instrument_id:     'aaa-111',
    symbol:            'RELIANCE',
    within_state_rank: 0.85,
    rs_rank_12m:       0.92,
    dwell_days:        14,
    ...overrides,
  }
}

function makePeers(count: number, currentId = 'aaa-111'): WithinStatePeer[] {
  return Array.from({ length: count }, (_, i) => makePeer({
    instrument_id:     i === 0 ? currentId : `peer-${i}`,
    symbol:            i === 0 ? 'RELIANCE' : `STOCK${i}`,
    within_state_rank: 1 - i * 0.03,
    rs_rank_12m:       0.9 - i * 0.02,
    dwell_days:        14 + i,
  }))
}

// ---------------------------------------------------------------------------
// Test 1: current stock is highlighted
// ---------------------------------------------------------------------------

describe('WithinStatePeers — current stock highlighted', () => {
  it('marks the current stock row with data-testid=current-peer-row', () => {
    const peers = makePeers(5, 'aaa-111')
    render(
      <WithinStatePeers
        peers={peers}
        currentInstrumentId="aaa-111"
        state="stage_2c"
      />,
    )
    expect(screen.getByTestId('current-peer-row')).toBeInTheDocument()
  })

  it('applies highlight class to current stock row', () => {
    const peers = makePeers(5, 'aaa-111')
    render(
      <WithinStatePeers
        peers={peers}
        currentInstrumentId="aaa-111"
        state="stage_2c"
      />,
    )
    const row = screen.getByTestId('current-peer-row')
    expect(row.className).toContain('bg-teal/10')
  })

  it('does not mark other rows as current', () => {
    const peers = makePeers(5, 'aaa-111')
    render(
      <WithinStatePeers
        peers={peers}
        currentInstrumentId="aaa-111"
        state="stage_2c"
      />,
    )
    // Only one current-peer-row in the document
    expect(screen.getAllByTestId('current-peer-row')).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// Test 2: state label mapping
// ---------------------------------------------------------------------------

describe('WithinStatePeers — state label mapping', () => {
  const cases: Array<[string, string]> = [
    ['stage_1',  'Stage 1 base'],
    ['stage_2a', 'Stage 2A fresh breakouts'],
    ['stage_2b', 'Stage 2B confirmed'],
    ['stage_2c', 'Stage 2C mature'],
    ['stage_3',  'Stage 3 tops'],
    ['stage_4',  'Stage 4 declines'],
  ]

  cases.forEach(([stateKey, expectedLabel]) => {
    it(`renders "${expectedLabel}" for state "${stateKey}"`, () => {
      render(
        <WithinStatePeers
          peers={makePeers(2)}
          currentInstrumentId="aaa-111"
          state={stateKey}
        />,
      )
      // Label appears in both heading and count line — check at least one element matches
      expect(screen.getAllByText(new RegExp(expectedLabel, 'i')).length).toBeGreaterThan(0)
    })
  })

  it('renders the peers table', () => {
    render(
      <WithinStatePeers
        peers={makePeers(3)}
        currentInstrumentId="aaa-111"
        state="stage_2c"
      />,
    )
    expect(screen.getByTestId('peers-table')).toBeInTheDocument()
  })

  it('renders empty state when peers array is empty', () => {
    render(
      <WithinStatePeers
        peers={[]}
        currentInstrumentId="aaa-111"
        state="stage_2c"
      />,
    )
    expect(screen.getByText(/No peers found/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 3: id anchor target exists (regression guard for #within-state-peers link)
// ---------------------------------------------------------------------------

describe('WithinStatePeers — id anchor target', () => {
  it('renders section with id="within-state-peers" when populated', () => {
    const { container } = render(
      <WithinStatePeers
        peers={makePeers(3)}
        currentInstrumentId="aaa-111"
        state="stage_2c"
      />,
    )
    const section = container.querySelector('#within-state-peers')
    expect(section).toBeInTheDocument()
    expect(section?.tagName.toLowerCase()).toBe('section')
  })

  it('renders section with id="within-state-peers" in empty-state branch', () => {
    const { container } = render(
      <WithinStatePeers
        peers={[]}
        currentInstrumentId="aaa-111"
        state="stage_2c"
      />,
    )
    const section = container.querySelector('#within-state-peers')
    expect(section).toBeInTheDocument()
    expect(section?.tagName.toLowerCase()).toBe('section')
  })
})
