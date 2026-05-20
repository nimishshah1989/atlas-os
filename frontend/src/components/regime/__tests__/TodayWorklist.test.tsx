import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { TodayWorklist } from '../TodayWorklist'
import type { WorklistData } from '../TodayWorklist'

const WORKLIST_DATA: WorklistData = {
  sectorsEnteredFavour: 3,
  freshBreakouts: 5,
  breakoutSymbols: ['ANANTRAJ', 'RELIANCE', 'INFY', 'TCS', 'WIPRO'],
  deterioratingCount: 2,
  deterioratingSymbols: ['BHARTIARTL', 'HINDUNILVR'],
}

describe('TodayWorklist', () => {
  it('renders the sectors-entered-favour count', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    const sectorLink = screen.getByTestId('worklist-sectors-link')
    // The count "3" is inside the sector link
    expect(sectorLink.textContent).toMatch(/3/)
  })

  it('sectors count links to /sectors', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    const sectorLink = screen.getByTestId('worklist-sectors-link')
    expect(sectorLink).toHaveAttribute('href', '/sectors')
  })

  it('renders the fresh breakouts count', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    expect(screen.getByText(/5/)).toBeInTheDocument()
  })

  it('breakout count links to the first breakout stock detail page', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    const breakoutLink = screen.getByTestId('worklist-breakout-link')
    expect(breakoutLink).toHaveAttribute('href', '/stocks/ANANTRAJ')
  })

  it('renders the deteriorating count', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    // The deteriorating count appears in a div — find it by the label next to it
    expect(screen.getByText('holdings deteriorating')).toBeInTheDocument()
    // The count 2 appears as a sibling span — verify via role or testid
    const deteriLabel = screen.getByText('holdings deteriorating')
    expect(deteriLabel.previousElementSibling?.textContent).toBe('2')
  })

  it('deteriorating section renders list items with LinkedTicker links', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    expect(screen.getByRole('link', { name: /BHARTIARTL/ })).toHaveAttribute('href', '/stocks/BHARTIARTL')
    expect(screen.getByRole('link', { name: /HINDUNILVR/ })).toHaveAttribute('href', '/stocks/HINDUNILVR')
  })

  it('breakout symbols are rendered as LinkedTicker anchors pointing to /stocks/[symbol]', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    // Each breakout symbol should be a link to its detail page
    const anantrajLink = screen.getByRole('link', { name: /ANANTRAJ/ })
    expect(anantrajLink).toHaveAttribute('href', '/stocks/ANANTRAJ')
    const relianceLink = screen.getByRole('link', { name: /RELIANCE/ })
    expect(relianceLink).toHaveAttribute('href', '/stocks/RELIANCE')
  })

  it('renders a LinkedTicker chip when there is exactly one breakout symbol', () => {
    const singleBreakoutData: WorklistData = {
      sectorsEnteredFavour: 1,
      freshBreakouts: 1,
      breakoutSymbols: ['RELIANCE'],
      deterioratingCount: 0,
      deterioratingSymbols: [],
    }
    render(<TodayWorklist data={singleBreakoutData} />)
    const relianceLink = screen.getByRole('link', { name: /RELIANCE/ })
    expect(relianceLink).toHaveAttribute('href', '/stocks/RELIANCE')
  })

  it('renders zero counts gracefully', () => {
    const emptyData: WorklistData = {
      sectorsEnteredFavour: 0,
      freshBreakouts: 0,
      breakoutSymbols: [],
      deterioratingCount: 0,
      deterioratingSymbols: [],
    }
    render(<TodayWorklist data={emptyData} />)
    const sectorLink = screen.getByTestId('worklist-sectors-link')
    expect(sectorLink).toHaveAttribute('href', '/sectors')
  })
})
