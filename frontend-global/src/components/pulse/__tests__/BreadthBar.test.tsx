/**
 * Breadth's one honesty rule: the denominator is part of the fact.
 *
 * `above_ema_200` is null until an instrument has 200 sessions. A fund listed in March has not
 * FAILED the 200-day test — nobody could run it. Counting those rows as "no" would report every
 * young fund as weak and quietly drag every breadth reading down, and the reading would still look
 * perfectly plausible, which is what makes it dangerous (rule #0).
 *
 * So the bar's width is the share of what was MEASURED, and both numbers are always printed.
 *
 * The numbers below are the real shape of this board: 503 S&P 500 members and 1,747 ETFs in the
 * universe at EOD 2026-09-08 (the live /health freshness rows and the /etfs count line), with a
 * measured count deliberately short of the membership, which is the case the rule is about.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BreadthBar } from '@/components/pulse/BreadthBar'

const text = (el: HTMLElement) => el.textContent ?? ''
const barWidth = (el: HTMLElement) =>
  (el.querySelector('span[style*="width"]') as HTMLElement | null)?.style.width ?? null

describe('a share is over what was measured, never over what was listed', () => {
  it('prints the count, the denominator and the share of the denominator', () => {
    // 312 of 487 measured, inside a 503-member index: the 16 unmeasured members are absent from
    // BOTH sides, not counted as failures.
    const { container } = render(<BreadthBar label="Above the 200-day" count={312} measured={487} />)
    expect(text(container)).toContain('64%')
    expect(text(container)).toContain('312/487')
    expect(barWidth(container)).toBe('64.1%')
  })

  it('does not draw a bar at all when nothing could be measured', () => {
    // Zero measured is "nobody could be asked", which is a different sentence from "none of them",
    // and 0/0 is not a share. A zero-width bar would read as the second.
    const { container } = render(<BreadthBar label="Above the 200-day" count={0} measured={0} />)
    expect(text(container)).toContain('not measured')
    expect(text(container)).not.toContain('0%')
    expect(barWidth(container)).toBeNull()
  })

  it('separates a real zero from an unmeasured one', () => {
    const { container } = render(<BreadthBar label="At a 52-week high" count={0} measured={1747} />)
    expect(text(container)).toContain('0%')
    expect(text(container)).toContain('0/1,747')
    // A bar of zero width, which is a real answer — not the absent bar of the case above.
    // (jsdom normalises "0.0%" to "0%"; the point is that the element exists and is empty.)
    expect(barWidth(container)).toBe('0%')
  })

  it('turns at the halfway mark, and the number is there either way', () => {
    const weak = render(<BreadthBar label="Beating SPY, 3 months" count={800} measured={1747} />).container
    const strong = render(<BreadthBar label="Beating SPY, 3 months" count={900} measured={1747} />).container
    const fill = (c: HTMLElement) => (c.querySelector('span[style*="width"]') as HTMLElement).style.background
    expect(fill(weak)).toContain('--color-neg')
    expect(fill(strong)).toContain('--color-pos')
    // Colour is never the only channel: both print their share.
    expect(text(weak)).toContain('46%')
    expect(text(strong)).toContain('52%')
  })
})
