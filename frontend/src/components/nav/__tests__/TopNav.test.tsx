import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('next/link', () => ({
  default: ({ href, children, className, onClick }: { href: string; children: React.ReactNode; className?: string; onClick?: () => void }) => (
    <a href={href} className={className} onClick={onClick}>{children}</a>
  ),
}))

const mockPathname = vi.fn(() => '/')
vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname(),
}))

import { TopNav, GROUPS } from '@/components/nav/TopNav'

// Every route that has a page.tsx today. The nav MUST NOT link anywhere else —
// a link to an unbuilt/retired page is a 404 shipped to users. When a new page
// lands, add its route here and the nav link in the same change.
const LIVE_ROUTES = new Set([
  '/', '/sectors', '/stocks', '/etfs', '/funds', '/health', '/methodology',
  '/admin', '/admin/thresholds', '/admin/data-status', '/admin/methodology', '/thresholds',
  '/desk', '/portfolios',
])

describe('TopNav', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPathname.mockReturnValue('/')
  })

  it('every nav href points at a page that exists (no 404s)', () => {
    for (const href of GROUPS.flatMap(g => g.links.map(l => l.href))) {
      expect(LIVE_ROUTES.has(href), `${href} has no page.tsx`).toBe(true)
    }
  })

  it('sections are the four live groups', () => {
    expect(GROUPS.map(g => g.key)).toEqual(['today', 'deepdive', 'portfolios', 'admin'])
  })

  it('renders the section labels', () => {
    render(<TopNav />)
    for (const label of ['MARKETS TODAY', 'DEEP DIVE', 'PORTFOLIOS', 'ADMIN']) {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1)
    }
  })

  it('activeGroup: /admin/thresholds activates ADMIN', () => {
    mockPathname.mockReturnValue('/admin/thresholds')
    render(<TopNav />)
    expect(document.querySelector('.fixed.top-11 span')?.textContent?.trim()).toBe('ADMIN')
  })

  it('activeGroup: /stocks activates DEEP DIVE', () => {
    mockPathname.mockReturnValue('/stocks')
    render(<TopNav />)
    expect(document.querySelector('.fixed.top-11 span')?.textContent?.trim()).toBe('DEEP DIVE')
  })
})
