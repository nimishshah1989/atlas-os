// frontend/src/components/v6/__tests__/GradeChip.test.tsx
// 8 test cases: 7 variant renders + 1 a11y label test.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GradeChip } from '../GradeChip'
import type { Grade } from '../GradeChip'

// ── Variant render tests (7 cases) ──────────────────────────────────────────

describe('GradeChip — variant renders', () => {
  it('renders AAA with signal-pos background and paper text', () => {
    const { container } = render(<GradeChip grade="AAA" />)
    const chip = container.querySelector('span')!
    expect(chip.textContent).toBe('AAA')
    expect(chip.className).toContain('bg-signal-pos')
    expect(chip.className).toContain('text-paper')
  })

  it('renders AA with signal-pos/70 background', () => {
    const { container } = render(<GradeChip grade="AA" />)
    const chip = container.querySelector('span')!
    expect(chip.textContent).toBe('AA')
    expect(chip.className).toContain('bg-signal-pos/70')
  })

  it('renders A with signal-pos/45 tint and signal-pos text', () => {
    const { container } = render(<GradeChip grade="A" />)
    const chip = container.querySelector('span')!
    expect(chip.textContent).toBe('A')
    expect(chip.className).toContain('bg-signal-pos/45')
    expect(chip.className).toContain('text-signal-pos')
  })

  it('renders BBB with signal-warn tint and signal-warn text', () => {
    const { container } = render(<GradeChip grade="BBB" />)
    const chip = container.querySelector('span')!
    expect(chip.textContent).toBe('BBB')
    expect(chip.className).toContain('bg-signal-warn/20')
    expect(chip.className).toContain('text-signal-warn')
  })

  it('renders BB with signal-neg/30 tint and signal-neg text', () => {
    const { container } = render(<GradeChip grade="BB" />)
    const chip = container.querySelector('span')!
    expect(chip.textContent).toBe('BB')
    expect(chip.className).toContain('bg-signal-neg/30')
    expect(chip.className).toContain('text-signal-neg')
  })

  it('renders B with signal-neg background and paper text', () => {
    const { container } = render(<GradeChip grade="B" />)
    const chip = container.querySelector('span')!
    expect(chip.textContent).toBe('B')
    expect(chip.className).toContain('bg-signal-neg')
    expect(chip.className).toContain('text-paper')
  })

  it('renders failed-gate with paper-deep inline style and ink-tertiary text', () => {
    const { container } = render(<GradeChip grade="failed-gate" />)
    const chip = container.querySelector('span')!
    // Display text is NO SIGNAL for failed-gate
    expect(chip.textContent).toBe('NO SIGNAL')
    expect(chip.className).toContain('text-ink-tertiary')
    // paper-deep (#F1ECDF) is applied via inline style (not in globals.css yet)
    expect(chip.style.backgroundColor).toBe('rgb(241, 236, 223)')
  })
})

// ── A11y test (1 case) ───────────────────────────────────────────────────────

describe('GradeChip — accessibility', () => {
  it.each<Grade>(['AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'failed-gate'])(
    'aria-label reads "Atlas grade %s" for all variants',
    (grade) => {
      render(<GradeChip grade={grade} />)
      const chip = screen.getByRole('img', { name: `Atlas grade ${grade}` })
      expect(chip).toBeInTheDocument()
    },
  )
})

// ── Size prop ────────────────────────────────────────────────────────────────

describe('GradeChip — size prop', () => {
  it('applies text-[10px] for size=sm', () => {
    const { container } = render(<GradeChip grade="AAA" size="sm" />)
    expect(container.querySelector('span')!.className).toContain('text-[10px]')
  })

  it('applies text-[11px] for size=md (default)', () => {
    const { container } = render(<GradeChip grade="AAA" />)
    expect(container.querySelector('span')!.className).toContain('text-[11px]')
  })
})

// ── Letter-spacing ───────────────────────────────────────────────────────────

describe('GradeChip — letter-spacing', () => {
  it('applies 0.14em letter-spacing via inline style', () => {
    const { container } = render(<GradeChip grade="AA" />)
    expect(container.querySelector('span')!.style.letterSpacing).toBe('0.14em')
  })
})
