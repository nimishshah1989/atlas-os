import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { InfoTooltip } from '../InfoTooltip'

describe('InfoTooltip', () => {
  // Existing regression: trigger button renders
  it('renders the trigger button', () => {
    render(<InfoTooltip content="Test explanation" />)
    expect(screen.getByRole('button', { name: /info/i })).toBeInTheDocument()
  })

  // Case 1: single-line — no translation prop → no ↳ arrow anywhere in the document
  it('single-line: renders definition text without arrow when translation is absent', () => {
    render(<InfoTooltip content="Information Coefficient measures rank correlation." />)
    expect(screen.getByRole('button', { name: /info/i })).toBeInTheDocument()
    // No ↳ character should appear anywhere in the rendered output
    expect(document.body.textContent).not.toContain('↳')
  })

  // Case 2: with translation — renders definition + ↳ + translation; describedby covers both
  it('with-translation: renders definition and ↳ translation line inside tooltip content', async () => {
    const user = userEvent.setup()
    render(
      <InfoTooltip
        content="IC (Information Coefficient)"
        translation="How well this signal predicts future returns"
      />
    )
    const trigger = screen.getByRole('button', { name: /info/i })

    // Focus the trigger to open the tooltip
    await user.tab()
    expect(trigger).toHaveFocus()

    // Radix renders content in both the visible tooltip and a hidden ARIA mirror.
    // Use getAllByText to handle both instances gracefully.
    const definitionEls = await screen.findAllByText('IC (Information Coefficient)')
    expect(definitionEls.length).toBeGreaterThanOrEqual(1)

    // Translation line with ↳ content should be present
    const translationEls = await screen.findAllByText(/How well this signal predicts future returns/)
    expect(translationEls.length).toBeGreaterThanOrEqual(1)

    // At least one translation element has the ink-tertiary class
    const styled = translationEls.find(el => el.className.includes('text-ink-tertiary'))
    expect(styled).toBeDefined()

    // The ↳ arrow character (U+21B3) should appear in the document
    expect(document.body.innerHTML).toContain('↳')

    // aria-describedby on trigger should point to the Tooltip.Content element
    const tooltipContentId = trigger.getAttribute('aria-describedby')
    expect(tooltipContentId).toBeTruthy()
    const tooltipContent = document.getElementById(tooltipContentId!)
    expect(tooltipContent).not.toBeNull()
    // The describedby region contains both definition and translation text
    expect(tooltipContent!.textContent).toContain('IC (Information Coefficient)')
    expect(tooltipContent!.textContent).toContain('How well this signal predicts future returns')
  })

  // Case 3: keyboard activation — focus trigger opens tooltip content; Esc closes it
  it('keyboard: focus trigger opens tooltip; Esc closes tooltip', async () => {
    const user = userEvent.setup()
    render(
      <InfoTooltip
        content="RS Velocity"
        translation="How fast this stock is gaining strength"
      />
    )

    // Tab to focus trigger → tooltip opens (Radix shows content on trigger focus)
    await user.tab()
    const trigger = screen.getByRole('button', { name: /info/i })
    expect(trigger).toHaveFocus()

    // Content should be present after focus
    const contentEls = await screen.findAllByText('RS Velocity')
    expect(contentEls.length).toBeGreaterThanOrEqual(1)

    // The Tooltip.Content node linked via aria-describedby should be open
    const tooltipContentId = trigger.getAttribute('aria-describedby')
    expect(tooltipContentId).toBeTruthy()
    const tooltipContent = document.getElementById(tooltipContentId!)
    expect(tooltipContent).not.toBeNull()
    expect(tooltipContent!.getAttribute('data-state')).toBe('instant-open')

    // Press Escape → tooltip closes (Radix removes the content node or sets data-state=closed)
    await user.keyboard('{Escape}')
    // After Escape the aria-describedby element should be gone or closed
    const afterEsc = document.getElementById(tooltipContentId!)
    const isClosed =
      afterEsc === null || afterEsc.getAttribute('data-state') === 'closed'
    expect(isClosed).toBe(true)
  })
})
