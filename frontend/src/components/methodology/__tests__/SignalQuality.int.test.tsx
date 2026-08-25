import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

// Rendered against the REAL journal rows — no fixture, no invented IC (rule #0). Skips in
// CI, where there is no .env.local and therefore no ATLAS_DB_URL.
const hasDb = Boolean(process.env.ATLAS_DB_URL)
const mod = hasDb
  ? await Promise.all([import('../SignalQuality'), import('@/lib/queries/signal_quality')])
  : null

function loaded(): NonNullable<typeof mod> {
  if (!mod) throw new Error('integration test ran without ATLAS_DB_URL — it should have skipped')
  return mod
}

describe.skipIf(!hasDb)('<SignalQuality/> on the live journal', () => {
  it('renders every lens, including the ones with no evidence', async () => {
    const [{ SignalQuality }, { getSignalQuality }] = loaded()
    render(<SignalQuality rows={await getSignalQuality()} />)
    for (const lens of ['policy', 'technical', 'flow', 'fundamental', 'valuation', 'catalyst', 'composite']) {
      expect(screen.getAllByRole('heading', { name: lens }).length, `${lens} card missing`).toBeGreaterThan(0)
    }
    // composite/large/wide reads +0.0003 — the weakest cell, and the one most worth seeing
    expect(screen.getAllByText('no evidence').length).toBeGreaterThan(0)
    // policy's structural caveat must sit next to policy's number
    expect(screen.getByText(/SECTOR call, not stock selection/)).toBeInTheDocument()
    // and the composite must be shown losing to its own inputs — counted off the live
    // rows, not asserted in prose. Real output on 2026-08-25: 3 of 6 wide, 5 of 6 narrow.
    expect(
      screen.getByText(/3 of the 6 lenses it blends score a higher IC .* and 5 of 6 in the narrow era/),
    ).toBeInTheDocument()
  })

  it('never prints a t-statistic or a corrupted decile spread', async () => {
    const [{ SignalQuality }, { getSignalQuality }] = loaded()
    const { container } = render(<SignalQuality rows={await getSignalQuality()} />)
    const text = container.textContent ?? ''
    // The defect footnote names +2811% deliberately — that is the explanation, not a
    // reading. What must never appear is the value rendered AS a return, which the page's
    // own percent formatter would emit as "+2811.3%".
    expect(text).not.toMatch(/[+−]\d{3,}\.\d%/)
    expect(text).not.toMatch(/t-stat\s*[:=]|t_stat/)
    expect(text).toMatch(/withheld/)
  })
})
