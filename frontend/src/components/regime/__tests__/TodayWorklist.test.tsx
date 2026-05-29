import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { TodayWorklist } from '../TodayWorklist'
import type { WorklistData } from '../TodayWorklist'

const WORKLIST_DATA: WorklistData = {
  sectorsEnteredFavour: 3,
  freshBreakouts: 5,
  breakoutSymbols: ['ANANTRAJ', 'RELIANCE', 'INFY', 'TCS', 'WIPRO'],
  breakoutDays: [
    { symbol: 'ANANTRAJ', days: 3 },
    { symbol: 'RELIANCE', days: 1 },
    { symbol: 'INFY', days: 7 },
    { symbol: 'TCS', days: 2 },
    { symbol: 'WIPRO', days: 4 },
  ],
  deterioratingCount: 2,
  deterioratingSymbols: ['BHARTIARTL', 'HINDUNILVR'],
  deterioratingDays: [
    { symbol: 'BHARTIARTL', days: 5 },
    { symbol: 'HINDUNILVR', days: 12 },
  ],
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
    const breakoutLink = screen.getByTestId('worklist-breakout-link')
    expect(breakoutLink.textContent).toMatch(/^5/)
  })

  it('breakout count links to the first breakout stock detail page', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    const breakoutLink = screen.getByTestId('worklist-breakout-link')
    expect(breakoutLink).toHaveAttribute('href', '/stocks/ANANTRAJ')
  })

  it('renders the deteriorating count', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    expect(screen.getByText('holdings deteriorating')).toBeInTheDocument()
    const deteriLink = screen.getByTestId('worklist-deterioration-link')
    expect(deteriLink.textContent).toMatch(/2/)
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

  it('renders a symbol pill when there is exactly one breakout symbol', () => {
    const singleBreakoutData: WorklistData = {
      sectorsEnteredFavour: 1,
      freshBreakouts: 1,
      breakoutSymbols: ['RELIANCE'],
      breakoutDays: [{ symbol: 'RELIANCE', days: 2 }],
      deterioratingCount: 0,
      deterioratingSymbols: [],
      deterioratingDays: [],
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
      breakoutDays: [],
      deterioratingCount: 0,
      deterioratingSymbols: [],
      deterioratingDays: [],
    }
    render(<TodayWorklist data={emptyData} />)
    const sectorLink = screen.getByTestId('worklist-sectors-link')
    expect(sectorLink).toHaveAttribute('href', '/sectors')
  })

  it('shows top-3 breakout symbols with day counters inside the breakout card', () => {
    render(<TodayWorklist data={WORKLIST_DATA} />)
    // Top 3 of breakoutDays = ANANTRAJ d3, RELIANCE d1, INFY d7
    expect(screen.getByText('d3')).toBeInTheDocument()
    expect(screen.getByText('d1')).toBeInTheDocument()
    expect(screen.getByText('d7')).toBeInTheDocument()
    // TCS + WIPRO are outside top-3 → not rendered
    expect(screen.queryByText(/^TCS$/)).not.toBeInTheDocument()
  })
})
