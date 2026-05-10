import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StateValuePair } from '../StateValuePair'

// Note: chips render abbreviated labels (from MOM_STATE_LABEL, VOL_STATE_LABEL in stock-formatters)
// e.g. "Accelerating" → "Accel", "Accumulation" → "Accum"

describe('StateValuePair', () => {
  it('renders the rs chip and scalar side by side', () => {
    render(<StateValuePair chipType="rs" state="Leader" scalar="87th" />)
    expect(screen.getByText('Leader')).toBeInTheDocument()
    expect(screen.getByText('87th')).toBeInTheDocument()
  })

  it('renders em-dash when scalar is null', () => {
    render(<StateValuePair chipType="rs" state="Strong" scalar={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders momentum chip type with abbreviated label', () => {
    render(<StateValuePair chipType="momentum" state="Accelerating" scalar="↑ 12d" />)
    // chip renders abbreviated "Accel"; full name available via title attr
    expect(screen.getByTitle('Accelerating')).toBeInTheDocument()
    expect(screen.getByText('↑ 12d')).toBeInTheDocument()
  })

  it('renders risk chip type', () => {
    render(<StateValuePair chipType="risk" state="Low" scalar="σ 18%" />)
    expect(screen.getByText('Low')).toBeInTheDocument()
    expect(screen.getByText('σ 18%')).toBeInTheDocument()
  })

  it('renders volume chip type with abbreviated label', () => {
    render(<StateValuePair chipType="volume" state="Accumulation" scalar="+2.3x" />)
    expect(screen.getByTitle('Accumulation')).toBeInTheDocument()
    expect(screen.getByText('+2.3x')).toBeInTheDocument()
  })
})
