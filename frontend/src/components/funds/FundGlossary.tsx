'use client'
import { useState } from 'react'
import { Info, X } from 'lucide-react'

type GlossaryEntry = { term: string; def: string; note?: string }

const ENTRIES: GlossaryEntry[] = [
  {
    term: 'NAV State',
    def: 'Price-momentum tier of the fund\'s net asset value relative to all universe funds. Ranked from Leader NAV (top ~5% RS) → Strong → Average → Emerging → Consolidating → Weak → Laggard NAV (bottom ~5%).',
    note: 'Same 7-tier scale as individual stocks — strips the word "NAV" for display.',
  },
  {
    term: 'Composition State',
    def: 'How well the fund\'s disclosed portfolio (sector + stock mix) aligns with the current market leadership. Aligned = most AUM in leader/strong areas · Mixed = partially aligned · Misaligned = most AUM in weak/laggard areas · N/A = no holdings disclosure available.',
  },
  {
    term: 'Holdings State',
    def: 'Quality of individual stock holdings based on each holding\'s own RS + momentum state. Strong-Holdings = most AUM in Leader/Strong stocks · Mixed-Holdings = balanced · Weak-Holdings = most AUM in Weak/Laggard stocks.',
  },
  {
    term: 'Recommendation',
    def: 'Overall investment decision derived from all three lenses plus market regime. Hold = passes minimum bar · Reduce = one or more lenses deteriorating · Exit = multiple failures or regime risk-off.',
    note: '"Recommended" requires all four gates to pass simultaneously.',
  },
  {
    term: 'RS Pctile',
    def: 'Relative Strength percentile vs all universe funds over the selected period (1M/3M/6M/1Y). 100 = strongest price momentum, 0 = weakest. Computed as a rolling rank.',
  },
  {
    term: 'RS Cat',
    def: 'Same Relative Strength rank but computed within the fund\'s category peers only. Useful for cross-category comparisons where absolute RS may be distorted by category-wide tailwinds.',
  },
  {
    term: 'Vol (63D)',
    def: 'Realized volatility over the last 63 trading days (~3 months), annualized. Higher vol = wider daily price swings. Used as bubble size in the Fund Map.',
  },
  {
    term: 'Gates (●●●●)',
    def: 'Four binary checks that individually feed the Recommendation. Left to right: Performance (fund RS vs category median) · Sectors (sector composition aligned) · Stocks (holdings quality) · Market (regime is Risk-On or neutral). Green = pass · Red = fail · Faded = insufficient data.',
  },
  {
    term: 'Comp Bar',
    def: 'Portfolio composition split: green = % AUM in Aligned sectors/stocks · grey = Neutral · red = Avoid. Width is proportional to AUM weight. Based on last disclosed portfolio (monthly).',
  },
  {
    term: 'Holdings Bar',
    def: 'Individual stock quality split: green = % AUM in Strong/Leader holdings · grey = Unknown state · red = Weak/Laggard holdings.',
  },
  {
    term: 'Weeks (In State)',
    def: 'How long the fund has been in its current NAV state without changing tier. A fund that has been a "Leader NAV" for 12 weeks has sustained strong price momentum.',
    note: 'Displayed as "52+" when data anomalies produce values above 260 weeks.',
  },
  {
    term: '1Y Ret',
    def: 'Trailing 12-month price return of the fund\'s NAV. Always raw, not risk-adjusted.',
  },
  {
    term: 'Max DD (1Y)',
    def: 'Maximum drawdown over the last 252 trading days — the largest peak-to-trough NAV decline in the past year. A measure of tail-risk, not average volatility.',
  },
  {
    term: 'Fund Map (Bubble Chart)',
    def: 'Scatter plot of all funds. X-axis = RS percentile · Y-axis = period return · Bubble size = volatility. Quadrants: Leaders (high RS, positive return) · Recovering (low RS, positive) · Fading (high RS, negative) · Laggards (low RS, negative). Click any bubble for the fund deep-dive.',
  },
]

export function FundGlossaryButton() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Column glossary"
        className="flex items-center gap-1 px-2 py-1 rounded-sm border border-paper-rule text-ink-tertiary hover:text-teal hover:border-teal transition-colors font-sans text-[11px]"
      >
        <Info className="w-3 h-3" />
        <span>Guide</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/20"
            onClick={() => setOpen(false)}
          />
          {/* Panel */}
          <div className="relative bg-paper border-l border-paper-rule shadow-xl w-full max-w-sm h-full overflow-y-auto">
            <div className="sticky top-0 bg-paper border-b border-paper-rule px-5 py-3 flex items-center justify-between">
              <span className="font-sans text-sm font-semibold text-ink-primary">Column Guide</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-ink-tertiary hover:text-ink-primary transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-5 py-4 space-y-5">
              {ENTRIES.map(e => (
                <div key={e.term}>
                  <div className="font-sans text-xs font-semibold text-ink-primary mb-0.5">{e.term}</div>
                  <div className="font-sans text-[11px] text-ink-secondary leading-relaxed">{e.def}</div>
                  {e.note && (
                    <div className="mt-0.5 font-sans text-[10px] text-ink-tertiary italic">{e.note}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
