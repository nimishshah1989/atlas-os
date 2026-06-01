// ETF tracking-error gate: te_60d is methodologically unreliable in v1 (computed
// against the wrong/misaligned benchmark series — sector/thematic ETFs show
// 17–29% "tracking error", and even broad_index medians ~17%, vs the <0.5%
// real-world figure). Garbage TE was failing the tracking gate for EVERY ETF and
// flipping the whole verdict to WAIT. Until the POST-V1 benchmark recompute, an
// implausibly-large TE must be treated as PROVISIONAL (non-gating), and the
// category thresholds must match the real etf_category values so the gate
// auto-resumes once TE becomes plausible.

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('server-only', () => ({}))

import { ETFGatesPanel, trackingGate, TE_DATA_SANITY_CEILING_BPS } from '../ETFGatesPanel'

describe('trackingGate — provisional handling of unreliable TE', () => {
  it('treats implausibly-large TE (garbage) as provisional/N-A, not FAIL', () => {
    // 1800 bps = 18% annualised TE — impossible for a passive ETF; data error.
    const g = trackingGate(1800, 'sector')
    expect(g.status).toBe('UNKNOWN')
    expect(g.detail).toMatch(/provisional/i)
  })

  it('keeps the sanity ceiling above any real ETF TE but below the garbage band', () => {
    expect(TE_DATA_SANITY_CEILING_BPS).toBeGreaterThanOrEqual(300)
    expect(TE_DATA_SANITY_CEILING_BPS).toBeLessThan(1000)
  })

  it('uses real etf_category thresholds: broad_index is tight (≤40 bps)', () => {
    expect(trackingGate(35, 'broad_index').status).toBe('PASS')
    expect(trackingGate(45, 'broad_index').status).toBe('FAIL')
  })

  it('uses real etf_category thresholds: sector is looser (≤80 bps)', () => {
    expect(trackingGate(60, 'sector').status).toBe('PASS')
    expect(trackingGate(120, 'sector').status).toBe('FAIL')
  })

  it('covers the full DB category vocabulary — debt is tight (≤50), not the loose default', () => {
    // debt + smart_beta are valid etf_category values (CHECK constraint); they
    // must not silently fall through to the 100 bps default.
    expect(trackingGate(45, 'debt').status).toBe('PASS')
    expect(trackingGate(60, 'debt').status).toBe('FAIL')   // would PASS under the 100 default — the bug
    expect(trackingGate(90, 'smart_beta').status).toBe('PASS')
  })

  it('still reports N/A when TE is unavailable', () => {
    expect(trackingGate(null, 'sector').status).toBe('UNKNOWN')
  })
})

describe('ETFGatesPanel — garbage TE must not flip the verdict to WAIT', () => {
  it('renders CLEAR when only the (garbage) TE would fail and all real gates pass', () => {
    render(
      <ETFGatesPanel
        adv20dInr={5e7}            // ₹5 cr ≥ 3 cr → PASS
        trackingErrorBps={2275}    // garbage → provisional, non-gating
        etfCategory="sector"
        premiumBps={5}             // within ±25 → PASS
        compositeScore={72}        // ≥ 50 → PASS
        sectorState="Overweight"   // not Avoid → PASS
        regimeState="Risk-On"      // not Risk-Off → PASS
      />,
    )
    expect(screen.getByText('CLEAR')).toBeInTheDocument()
    // Must not falsely claim "all 6 gates pass" while TE is N/A; the note
    // honestly reports the pass/N-A split instead.
    expect(screen.queryByText(/All 6 gates pass/)).not.toBeInTheDocument()
    expect(screen.getByText(/No gate fails \(.*N\/A\)/)).toBeInTheDocument()
  })
})
