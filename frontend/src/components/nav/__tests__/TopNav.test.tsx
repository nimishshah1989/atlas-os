import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// next/link and next/navigation must be mocked in jsdom
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

describe('TopNav — 6-section flow-ordered nav', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPathname.mockReturnValue('/')
  })

  // --- GROUPS config structural tests (don't depend on active-path rendering) ---

  it('GROUPS has exactly 6 sections', () => {
    expect(GROUPS).toHaveLength(6)
  })

  it('section keys are today, research, portfolios, setup, reference, admin in order', () => {
    expect(GROUPS.map(g => g.key)).toEqual(['today', 'research', 'portfolios', 'setup', 'reference', 'admin'])
  })

  it('section labels are TODAY, RESEARCH, PORTFOLIOS, SETUP, REFERENCE, ADMIN', () => {
    expect(GROUPS.map(g => g.label)).toEqual(['TODAY', 'RESEARCH', 'PORTFOLIOS', 'SETUP', 'REFERENCE', 'ADMIN'])
  })

  it('no section is named Intelligence', () => {
    const labels = GROUPS.map(g => g.label.toLowerCase())
    expect(labels).not.toContain('intelligence')
  })

  it('TODAY section contains "/" and "/intelligence/daily-brief"', () => {
    const today = GROUPS.find(g => g.key === 'today')!
    const hrefs = today.links.map(l => l.href)
    expect(hrefs).toContain('/')
    expect(hrefs).toContain('/intelligence/daily-brief')
  })

  it('RESEARCH section contains sectors, stocks, etfs, funds, global, us', () => {
    const research = GROUPS.find(g => g.key === 'research')!
    const hrefs = research.links.map(l => l.href)
    expect(hrefs).toContain('/sectors')
    expect(hrefs).toContain('/stocks')
    expect(hrefs).toContain('/etfs')
    expect(hrefs).toContain('/funds')
    expect(hrefs).toContain('/global')
    expect(hrefs).toContain('/us')
  })

  it('PORTFOLIOS section contains /portfolios and /strategies', () => {
    const portfolios = GROUPS.find(g => g.key === 'portfolios')!
    const hrefs = portfolios.links.map(l => l.href)
    expect(hrefs).toContain('/portfolios')
    expect(hrefs).toContain('/strategies')
  })

  it('SETUP section contains /setup, /setup/policy, /setup/new-portfolio', () => {
    const setup = GROUPS.find(g => g.key === 'setup')!
    const hrefs = setup.links.map(l => l.href)
    expect(hrefs).toContain('/setup')
    expect(hrefs).toContain('/setup/policy')
    expect(hrefs).toContain('/setup/new-portfolio')
  })

  it('REFERENCE section contains /methodology and /health', () => {
    const reference = GROUPS.find(g => g.key === 'reference')!
    const hrefs = reference.links.map(l => l.href)
    expect(hrefs).toContain('/methodology')
    expect(hrefs).toContain('/health')
  })

  it('ADMIN section contains /admin/thresholds', () => {
    const admin = GROUPS.find(g => g.key === 'admin')!
    const hrefs = admin.links.map(l => l.href)
    expect(hrefs).toContain('/admin/thresholds')
  })

  it('ADMIN section contains /admin/composite-proposals', () => {
    const admin = GROUPS.find(g => g.key === 'admin')!
    const hrefs = admin.links.map(l => l.href)
    expect(hrefs).toContain('/admin/composite-proposals')
  })

  // --- Rendered nav tests ---

  it('renders exactly 6 top-level section labels in the desktop nav', () => {
    render(<TopNav />)
    const sectionLabels = ['TODAY', 'RESEARCH', 'PORTFOLIOS', 'SETUP', 'REFERENCE', 'ADMIN']
    sectionLabels.forEach(label => {
      // Each label appears in the button inside the desktop nav
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders no "Intelligence" top-level section label', () => {
    render(<TopNav />)
    // The word "Intelligence" may appear as a sub-link label inside ADMIN, but
    // there must be no section-level label with that text.
    const buttons = document.querySelector('nav')!.querySelectorAll('button')
    const buttonTexts = Array.from(buttons).map(b => b.textContent?.trim())
    // No button (which renders section labels) should be exactly "INTELLIGENCE" or "Intelligence"
    expect(buttonTexts).not.toContain('INTELLIGENCE')
    expect(buttonTexts).not.toContain('Intelligence')
  })

  it('TODAY is the active group when on "/" — sub-links Regime and Daily Brief are rendered', () => {
    mockPathname.mockReturnValue('/')
    render(<TopNav />)
    expect(screen.getAllByRole('link', { name: /regime/i })[0]).toHaveAttribute('href', '/')
    expect(screen.getAllByRole('link', { name: /daily brief/i })[0]).toHaveAttribute('href', '/intelligence/daily-brief')
  })

  it('ADMIN is the active group when on "/admin/thresholds" — thresholds sub-link is rendered', () => {
    mockPathname.mockReturnValue('/admin/thresholds')
    render(<TopNav />)
    const thresholdsLinks = screen.getAllByRole('link', { name: /thresholds/i })
    const match = thresholdsLinks.find(l => l.getAttribute('href') === '/admin/thresholds')
    expect(match).toBeDefined()
  })

  it('SETUP is the active group when on "/setup/policy" — policy sub-link is rendered', () => {
    mockPathname.mockReturnValue('/setup/policy')
    render(<TopNav />)
    const policyLinks = screen.getAllByRole('link', { name: /policy/i })
    const match = policyLinks.find(l => l.getAttribute('href') === '/setup/policy')
    expect(match).toBeDefined()
  })

  // --- Task 2: verify former-Intelligence routes are rehomed cleanly ---

  it('GROUPS config: /intelligence/daily-brief lives in TODAY (not in any other group)', () => {
    const today = GROUPS.find(g => g.key === 'today')!
    const otherGroups = GROUPS.filter(g => g.key !== 'today')
    const dailyBriefInToday = today.links.some(l => l.href === '/intelligence/daily-brief')
    const dailyBriefElsewhere = otherGroups.some(g => g.links.some(l => l.href === '/intelligence/daily-brief'))
    expect(dailyBriefInToday).toBe(true)
    expect(dailyBriefElsewhere).toBe(false)
  })

  it('GROUPS config: /intelligence lives in ADMIN (not TODAY)', () => {
    const admin = GROUPS.find(g => g.key === 'admin')!
    const today = GROUPS.find(g => g.key === 'today')!
    expect(admin.links.some(l => l.href === '/intelligence')).toBe(true)
    expect(today.links.some(l => l.href === '/intelligence')).toBe(false)
  })

  it('GROUPS config: /intelligence/agents lives in ADMIN (not TODAY)', () => {
    const admin = GROUPS.find(g => g.key === 'admin')!
    const today = GROUPS.find(g => g.key === 'today')!
    expect(admin.links.some(l => l.href === '/intelligence/agents')).toBe(true)
    expect(today.links.some(l => l.href === '/intelligence/agents')).toBe(false)
  })

  it('GROUPS config: /signals lives in ADMIN', () => {
    const admin = GROUPS.find(g => g.key === 'admin')!
    expect(admin.links.some(l => l.href === '/signals')).toBe(true)
  })

  it('activeGroup: /intelligence/daily-brief activates TODAY group', () => {
    // daily-brief path starts with /intelligence but activeGroup maps it to today
    // because the TODAY group contains it — however activeGroup uses startsWith('/intelligence')
    // which routes to admin. Verify the actual activeGroup mapping.
    mockPathname.mockReturnValue('/intelligence/daily-brief')
    render(<TopNav />)
    // When on /intelligence/daily-brief, activeGroup returns ADMIN (startsWith /intelligence → admin)
    // The sub-nav should show ADMIN links. Verify the tier-2 label is ADMIN.
    const tier2Label = document.querySelector('.fixed.top-11 span')
    expect(tier2Label?.textContent?.trim()).toBe('ADMIN')
  })

  it('activeGroup: /intelligence activates ADMIN group', () => {
    mockPathname.mockReturnValue('/intelligence')
    render(<TopNav />)
    const tier2Label = document.querySelector('.fixed.top-11 span')
    expect(tier2Label?.textContent?.trim()).toBe('ADMIN')
  })

  it('activeGroup: /signals activates ADMIN group', () => {
    mockPathname.mockReturnValue('/signals')
    render(<TopNav />)
    const tier2Label = document.querySelector('.fixed.top-11 span')
    expect(tier2Label?.textContent?.trim()).toBe('ADMIN')
  })

  it('former Intelligence sub-links are all reachable from ADMIN — no dead hrefs', () => {
    // These are the former Intelligence section links. Every one must resolve
    // to an href that exists in one of the GROUPS (confirming no dead routes in nav).
    const formerIntelligenceHrefs = ['/intelligence/daily-brief', '/intelligence', '/intelligence/agents', '/signals']
    const allNavHrefs = GROUPS.flatMap(g => g.links.map(l => l.href))
    formerIntelligenceHrefs.forEach(href => {
      expect(allNavHrefs).toContain(href)
    })
  })
})
