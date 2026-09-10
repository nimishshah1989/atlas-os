/**
 * The tooltip has to survive the element it is nested in, and this test exists because it did not.
 *
 * Its usual home is a table header, and `.panel table th` in globals.css sets `white-space: nowrap`
 * so a column label never wraps, plus `text-transform: uppercase` for the desk's small caps. A
 * <span> inside that <th> inherits both. The FM caught it on /sectors: a three-sentence
 * explanation rendered as ONE LINE OF CAPITALS running off the right edge of the screen, with the
 * panel's own `w-[290px]` doing nothing, because nowrap makes content overflow a fixed width
 * rather than wrap inside it.
 *
 * jsdom does not do cascade or layout, so this cannot assert the rendered box. What it CAN pin is
 * that the panel carries the explicit resets — which is the actual fix, and the thing a later edit
 * to the class list would silently drop.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { InfoTip } from '@/components/ui/InfoTip'

describe('InfoTip', () => {
  const panel = () => {
    const { container } = render(
      <InfoTip title="What the score is measured over">Everything the scorer graded.</InfoTip>,
    )
    return container.querySelector<HTMLElement>('[role="tooltip"]')
  }

  it('resets the text properties a table header would otherwise lend it', () => {
    const tip = panel()
    expect(tip).not.toBeNull()
    for (const reset of ['whitespace-normal', 'normal-case', 'tracking-normal', 'font-normal']) {
      expect(tip?.className, reset).toContain(reset)
    }
  })

  it('is bounded by the viewport as well as by its own width', () => {
    // 290px is the design width; the max-width is what stops a narrow screen from being the one
    // place the panel still leaves the page.
    const tip = panel()
    expect(tip?.className).toContain('w-[290px]')
    expect(tip?.className).toContain('max-w-[calc(100vw-32px)]')
  })

  it('names the button for a reader who cannot see the glyph', () => {
    const { container } = render(<InfoTip title="Breadth">Share above the 200-day line.</InfoTip>)
    expect(container.querySelector('button')?.getAttribute('aria-label')).toBe('About Breadth')
  })
})
