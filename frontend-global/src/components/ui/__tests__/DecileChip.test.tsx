/**
 * Structure-only render test. Nothing here is a market number: a decile is 1–10 by definition
 * (ntile(10) within the peer group, cut on read), and what is under test is that each step lands
 * on its own token of the ramp globals.css defines, that the number is PRINTED inside the chip so
 * the colour is never the only channel, and that an absent rank is an em dash rather than a
 * bottom-decile chip — which would be a rank nobody computed (rule #0).
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DecileChip, LeaderMark } from '@/components/ui/DecileChip'

describe('DecileChip', () => {
  it('paints each decile with its own ramp token and prints the number inside it', () => {
    for (let n = 1; n <= 10; n += 1) {
      const { container, unmount } = render(<DecileChip decile={n} />)
      const chip = container.querySelector<HTMLElement>('.decile-chip')
      expect(chip?.style.backgroundColor).toBe(`var(--decile-${n})`)
      expect(chip?.textContent).toBe(String(n))
      expect(chip?.dataset.decile).toBe(String(n))
      unmount()
    }
  })

  it('is an em dash with no chip at all when the row is not ranked', () => {
    const { container } = render(<DecileChip decile={null} />)
    expect(container.querySelector('.decile-chip')).toBeNull()
    expect(container.textContent).toBe('—')
  })

  it('carries the population its rank was cut in, for a reader and for a screen reader', () => {
    const { container } = render(<DecileChip decile={4} title="ranked 4 of 34 in Equity · Sector" />)
    const chip = container.querySelector<HTMLElement>('.decile-chip')
    expect(chip?.title).toBe('ranked 4 of 34 in Equity · Sector')
    expect(chip?.getAttribute('aria-label')).toBe('Decile 4 of 10, ranked 4 of 34 in Equity · Sector')
  })

  it('marks the top decile as the Leader, in a word and not only in a colour', () => {
    const { container } = render(<DecileChip decile={10} />)
    expect(container.querySelector<HTMLElement>('.decile-chip')?.dataset.leader).toBe('')
    expect(render(<LeaderMark decile={10} />).container.textContent).toBe('Leader')
    expect(render(<LeaderMark decile={9} />).container.textContent).toBe('')
    expect(render(<LeaderMark decile={null} />).container.textContent).toBe('')
  })
})
