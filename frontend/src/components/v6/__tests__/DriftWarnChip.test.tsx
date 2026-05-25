// frontend/src/components/v6/__tests__/DriftWarnChip.test.tsx
//
// 3 test cases for DriftWarnChip (E.4):
//   1. drift_warn → renders chip with correct copy + bg-signal-warn class
//   2. healthy    → returns null (container.firstChild === null)
//   3. deprecated → renders chip with bg-signal-neg + "Deprecated" copy

import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { DriftWarnChip } from '../DriftWarnChip'

// ── Mock InfoTooltip (Radix Tooltip requires DOM environment quirks) ──────────
vi.mock('@/components/ui/InfoTooltip', () => ({
  InfoTooltip: ({ content }: { content: string }) => (
    <span data-testid="info-tooltip" data-content={content} />
  ),
}))

// ── Test 1: drift_warn ───────────────────────────────────────────────────────

describe('DriftWarnChip — drift_warn', () => {
  it('renders chip with correct copy and bg-signal-warn class', () => {
    const { container } = render(<DriftWarnChip driftStatus="drift_warn" />)
    const chip = container.querySelector('[role="status"]') as HTMLElement

    expect(chip).not.toBeNull()

    // Text content includes both parts of the label
    expect(chip.textContent).toContain('Drift flagged')
    expect(chip.textContent).toContain('maintainer reviewing')

    // Uses bg-signal-warn token
    expect(chip.className).toContain('bg-signal-warn')

    // ARIA label for drift_warn variant
    expect(chip.getAttribute('aria-label')).toBe(
      'Drift warning: maintainer reviewing this cell',
    )
  })
})

// ── Test 2: healthy ──────────────────────────────────────────────────────────

describe('DriftWarnChip — healthy', () => {
  it('renders null — container.firstChild is null', () => {
    const { container } = render(<DriftWarnChip driftStatus="healthy" />)
    expect(container.firstChild).toBeNull()
  })
})

// ── Test 3: deprecated ───────────────────────────────────────────────────────

describe('DriftWarnChip — deprecated', () => {
  it('renders chip with bg-signal-neg and "Deprecated" copy', () => {
    const { container } = render(<DriftWarnChip driftStatus="deprecated" />)
    const chip = container.querySelector('[role="status"]') as HTMLElement

    expect(chip).not.toBeNull()

    // Text includes "Deprecated"
    expect(chip.textContent).toContain('Deprecated')

    // Uses bg-signal-neg token
    expect(chip.className).toContain('bg-signal-neg')

    // ARIA label for deprecated variant (distinct from drift_warn)
    expect(chip.getAttribute('aria-label')).toBe(
      'Deprecated: do not act on new signals from this cell',
    )
  })
})

// ── Bonus: null driftStatus ──────────────────────────────────────────────────

describe('DriftWarnChip — null', () => {
  it('renders null when driftStatus is null', () => {
    const { container } = render(<DriftWarnChip driftStatus={null} />)
    expect(container.firstChild).toBeNull()
  })
})
