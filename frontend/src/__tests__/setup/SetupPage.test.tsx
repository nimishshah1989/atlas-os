// Tests for src/app/setup/page.tsx
// Covers: renders orientation text, two card links to /setup/policy and /setup/new-portfolio

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock next/link so it renders a plain <a>
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

// Import after mocks (page.tsx is a simple RSC shell with no async data)
import SetupPage from '@/app/setup/page'

describe('/setup — onboarding landing', () => {
  it('renders a link to /setup/policy', () => {
    render(<SetupPage />)
    const link = screen.getByRole('link', { name: /policy/i })
    expect(link).toHaveAttribute('href', '/setup/policy')
  })

  it('renders a link to /setup/new-portfolio', () => {
    render(<SetupPage />)
    const link = screen.getByRole('link', { name: /new portfolio/i })
    expect(link).toHaveAttribute('href', '/setup/new-portfolio')
  })

  it('renders orientation text about configuring Atlas', () => {
    render(<SetupPage />)
    // Some text describing purpose of this section
    expect(screen.getByText(/configure/i)).toBeInTheDocument()
  })
})
