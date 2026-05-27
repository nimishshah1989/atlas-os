// frontend/src/components/v6/__tests__/SwitchProposalsBanner.test.tsx
//
// 4 test cases:
//   1. silent-when-zero: renders nothing when proposals is []
//   2. summary-text: shows count + "of your fund holdings should switch"
//   3. expand: click expands to show source/target fund pairs
//   4. methodology-note: expanded state shows methodology note

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SwitchProposalsBanner } from '../SwitchProposalsBanner'
import type { SwitchProposal } from '@/lib/queries/v6/switch_proposals'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ONE_PROPOSAL: SwitchProposal = {
  source_iid: 'aaaa0000-0000-0000-0000-000000000001',
  source_code: 'SC001',
  source_name: 'HDFC Large Cap Fund',
  source_peer_quartile: 'Q3',
  target_iid: 'bbbb0000-0000-0000-0000-000000000002',
  target_code: 'SC002',
  target_name: 'Axis Bluechip Fund',
  target_peer_quartile: 'Q2',
  category: 'India Fund Large-Cap',
}

const THREE_PROPOSALS: SwitchProposal[] = [
  ONE_PROPOSAL,
  {
    source_iid: 'cccc0000-0000-0000-0000-000000000003',
    source_code: 'SC003',
    source_name: 'Aditya Birla Mid Cap',
    source_peer_quartile: 'Q4',
    target_iid: 'dddd0000-0000-0000-0000-000000000004',
    target_code: 'SC004',
    target_name: 'Mirae Asset Midcap',
    target_peer_quartile: 'Q1',
    category: 'India Fund Mid-Cap',
  },
  {
    source_iid: 'eeee0000-0000-0000-0000-000000000005',
    source_code: 'SC005',
    source_name: 'SBI Small Cap Fund',
    source_peer_quartile: 'Q3',
    target_iid: null,
    target_code: null,
    target_name: null,
    target_peer_quartile: null,
    category: 'India Fund Small-Cap',
  },
]

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SwitchProposalsBanner', () => {
  // -------------------------------------------------------------------------
  // Case 1: silent when proposals is empty
  // -------------------------------------------------------------------------
  it('renders nothing when proposals is empty', () => {
    const { container } = render(<SwitchProposalsBanner proposals={[]} />)
    expect(container.firstChild).toBeNull()
  })

  // -------------------------------------------------------------------------
  // Case 2: summary text for single proposal
  // -------------------------------------------------------------------------
  it('shows singular summary text when 1 proposal', () => {
    render(<SwitchProposalsBanner proposals={[ONE_PROPOSAL]} />)
    expect(
      screen.getByText('1 of your fund holdings should switch'),
    ).toBeDefined()
  })

  // -------------------------------------------------------------------------
  // Case 3: expand to show source/target pairs
  // -------------------------------------------------------------------------
  it('expands to show proposal details on click', () => {
    render(<SwitchProposalsBanner proposals={[ONE_PROPOSAL]} />)

    // Proposals not visible before click
    expect(screen.queryByText('HDFC Large Cap Fund')).toBeNull()

    // Click the button to expand (button is inside the region, use getByRole 'button')
    fireEvent.click(screen.getByRole('button'))

    // Now source and target names are visible
    expect(screen.getByText('HDFC Large Cap Fund')).toBeDefined()
    expect(screen.getByText('Axis Bluechip Fund')).toBeDefined()
    expect(screen.getByText('India Fund Large-Cap')).toBeDefined()
  })

  // -------------------------------------------------------------------------
  // Case 4: methodology note shown when expanded
  // -------------------------------------------------------------------------
  it('shows methodology note when expanded with 3 proposals', () => {
    render(<SwitchProposalsBanner proposals={THREE_PROPOSALS} />)

    // Click to expand
    fireEvent.click(screen.getByRole('button'))

    // Count summary uses plural
    expect(screen.getByText('3 of your fund holdings should switch')).toBeDefined()

    // Methodology note appears
    expect(screen.getByText(/SWITCH criteria/i)).toBeDefined()

    // No target case: shows "No qualifying fund found" message
    expect(screen.getByText(/No qualifying fund found in India Fund Small-Cap/i)).toBeDefined()
  })
})
