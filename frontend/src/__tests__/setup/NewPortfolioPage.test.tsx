// Tests for src/components/setup/NewPortfolioForm.tsx
// Covers:
//   - Renders name input, instrument_universe select, note about house-default policy
//   - Submit with valid data calls POST /api/portfolio/create
//   - Shows error on missing name
//   - Shows error on API failure (error_code envelope)
//   - Shows success with link to new portfolio on creation

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

import { NewPortfolioForm } from '@/components/setup/NewPortfolioForm'

describe('NewPortfolioForm — rendering', () => {
  it('renders a name text input', () => {
    render(<NewPortfolioForm />)
    expect(screen.getByLabelText(/portfolio name/i)).toBeInTheDocument()
  })

  it('renders an instrument_universe select with the four universe options', () => {
    render(<NewPortfolioForm />)
    const select = screen.getByLabelText(/instrument universe/i)
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /direct equity/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /etf/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /mutual fund/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /mixed/i })).toBeInTheDocument()
  })

  it('renders a note about inheriting house-default policy', () => {
    render(<NewPortfolioForm />)
    expect(screen.getByText(/house.default/i)).toBeInTheDocument()
  })

  it('renders a submit button', () => {
    render(<NewPortfolioForm />)
    expect(screen.getByRole('button', { name: /create/i })).toBeInTheDocument()
  })
})

describe('NewPortfolioForm — validation', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows error when name is empty on submit', async () => {
    render(<NewPortfolioForm />)
    fireEvent.click(screen.getByRole('button', { name: /create/i }))
    await waitFor(() => {
      expect(screen.getByTestId('form-error')).toHaveTextContent(/name.*required/i)
    })
  })

  it('does not call fetch when name is empty', async () => {
    const mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
    render(<NewPortfolioForm />)
    fireEvent.click(screen.getByRole('button', { name: /create/i }))
    await waitFor(() => {
      expect(screen.getByTestId('form-error')).toBeInTheDocument()
    })
    expect(mockFetch).not.toHaveBeenCalled()
  })
})

describe('NewPortfolioForm — submit flow', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('POSTs to /api/portfolio/create with name and instrument_universe', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { id: 'new-portfolio-uuid', name: 'My New Portfolio' } }),
    })
    vi.stubGlobal('fetch', mockFetch)

    render(<NewPortfolioForm />)

    fireEvent.change(screen.getByLabelText(/portfolio name/i), {
      target: { value: 'My New Portfolio' },
    })
    fireEvent.change(screen.getByLabelText(/instrument universe/i), {
      target: { value: 'etf' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create/i }))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/portfolio/create',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.name).toBe('My New Portfolio')
    expect(body.instrument_universe).toBe('etf')
  })

  it('shows success state with link to new portfolio on creation', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { id: 'new-portfolio-uuid', name: 'My New Portfolio' } }),
    })
    vi.stubGlobal('fetch', mockFetch)

    render(<NewPortfolioForm />)

    fireEvent.change(screen.getByLabelText(/portfolio name/i), {
      target: { value: 'My New Portfolio' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create/i }))

    await waitFor(() => {
      expect(screen.getByTestId('create-success')).toBeInTheDocument()
    })

    // Should have a link to the new portfolio
    const link = screen.getByRole('link', { name: /view portfolio/i })
    expect(link).toHaveAttribute('href', '/portfolios/new-portfolio-uuid')
  })

  it('shows API error message on failure', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error_code: 'validation_error', message: 'Name must be unique' }),
    })
    vi.stubGlobal('fetch', mockFetch)

    render(<NewPortfolioForm />)

    fireEvent.change(screen.getByLabelText(/portfolio name/i), {
      target: { value: 'Duplicate Name' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create/i }))

    await waitFor(() => {
      expect(screen.getByTestId('form-error')).toHaveTextContent('Name must be unique')
    })
  })

  it('disables button while submitting', async () => {
    let resolveCreate!: (v: unknown) => void
    const mockFetch = vi.fn().mockReturnValueOnce(
      new Promise((resolve) => { resolveCreate = resolve }),
    )
    vi.stubGlobal('fetch', mockFetch)

    render(<NewPortfolioForm />)

    fireEvent.change(screen.getByLabelText(/portfolio name/i), {
      target: { value: 'My Portfolio' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create/i }))

    // Button should be disabled while in-flight
    expect(screen.getByRole('button', { name: /creat/i })).toBeDisabled()

    resolveCreate({
      ok: true,
      json: async () => ({ data: { id: 'uuid-123', name: 'My Portfolio' } }),
    })
  })
})
