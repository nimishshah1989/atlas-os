import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FundMetricTiles } from '../FundMetricTiles'
import type { FilterChip, TileCounts } from '../FundPageClient'

const TILE_COUNTS: TileCounts = {
  n_recommended: 20,
  n_hold: 40,
  n_leader_nav: 30,
  n_aligned: 50,
  n_strong_hold: 15,
  n_suspended: 5,
  n_weak_hold: 10,
}

const BASE_PROPS = {
  tileCounts: TILE_COUNTS,
  medianRsPctile: 0.55,
  medianReturn: 0.08,
  period: '3M' as const,
  funds: Array.from({ length: 191 }, (_, i) => ({ mstar_id: `F${i}` })) as any,
  activeFilter: 'all' as FilterChip,
  onTileClick: vi.fn(),
}

describe('FundMetricTiles', () => {
  it('renders all 7 tile labels', () => {
    render(<FundMetricTiles {...BASE_PROPS} />)
    expect(screen.getByText(/RECOMMENDED/i)).toBeInTheDocument()
    // Use getAllByText for HOLD since STRONG HOLD also contains "HOLD"
    const holdLabels = screen.getAllByText(/HOLD/i)
    expect(holdLabels.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/LEADER NAV/i)).toBeInTheDocument()
    expect(screen.getByText(/ALIGNED/i)).toBeInTheDocument()
    expect(screen.getByText(/STRONG HOLD/i)).toBeInTheDocument()
    expect(screen.getByText(/MEDIAN RS/i)).toBeInTheDocument()
    expect(screen.getByText(/3M RET/i)).toBeInTheDocument()
  })

  it('shows correct count values', () => {
    render(<FundMetricTiles {...BASE_PROPS} />)
    expect(screen.getByText('20')).toBeInTheDocument()   // RECOMMENDED
    expect(screen.getByText('40')).toBeInTheDocument()   // HOLD
    expect(screen.getByText('30')).toBeInTheDocument()   // LEADER NAV
  })

  it('shows aria-pressed=false for non-active clickable tiles', () => {
    render(<FundMetricTiles {...BASE_PROPS} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBe(5)
    buttons.forEach(btn => expect(btn).toHaveAttribute('aria-pressed', 'false'))
  })

  it('shows aria-pressed=true for the active tile', () => {
    render(<FundMetricTiles {...BASE_PROPS} activeFilter="recommended" />)
    const buttons = screen.getAllByRole('button')
    const active = buttons.find(b => b.getAttribute('aria-pressed') === 'true')
    expect(active).toBeTruthy()
  })

  it('calls onTileClick when a clickable tile is clicked', () => {
    const onTileClick = vi.fn()
    render(<FundMetricTiles {...BASE_PROPS} onTileClick={onTileClick} />)
    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[0])
    expect(onTileClick).toHaveBeenCalledOnce()
  })

  it('calls onTileClick on Enter keypress', () => {
    const onTileClick = vi.fn()
    render(<FundMetricTiles {...BASE_PROPS} onTileClick={onTileClick} />)
    const buttons = screen.getAllByRole('button')
    fireEvent.keyDown(buttons[0], { key: 'Enter' })
    expect(onTileClick).toHaveBeenCalledOnce()
  })

  it('shows em-dash for STRONG HOLD sub when n_hold is 0', () => {
    const props = { ...BASE_PROPS, tileCounts: { ...TILE_COUNTS, n_hold: 0, n_strong_hold: 0 } }
    render(<FundMetricTiles {...props} />)
    // Strong hold sub should show em-dash when n_hold === 0
    // Count the em-dashes — at least one should appear
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('shows funds.length in subtext', () => {
    render(<FundMetricTiles {...BASE_PROPS} />)
    expect(screen.getByText(/191 of 592/)).toBeInTheDocument()
  })

  it('shows em-dash for median return when null', () => {
    render(<FundMetricTiles {...BASE_PROPS} medianReturn={null} />)
    // The MEDIAN RET tile should show —
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })
})
