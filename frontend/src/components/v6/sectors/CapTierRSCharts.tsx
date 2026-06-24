'use client'

// CapTierRSCharts — relative strength of each cap tier vs Nifty 500 as DIRECT TradingView
// Advanced-Chart ratio embeds (tier index ÷ NSE:CNX500). A rising line = the tier is
// outperforming the broad market. Zero Atlas data — TV's data and servers. Symbols are the
// ones confirmed from TradingView's production bundles (handoff 2026-06-23); ratio symbols
// render in the Advanced-Chart widget (FM-verified in a real browser).
import { TVRatioChart } from '@/components/charts/TVRatioChart'

const TIERS: { symbol: string; label: string }[] = [
  { symbol: 'NSE:NIFTYSMLCAP250/NSE:CNX500', label: 'Smallcap 250 ÷ Nifty 500' },
  { symbol: 'NSE:NIFTYMIDCAP150/NSE:CNX500', label: 'Midcap 150 ÷ Nifty 500' },
  { symbol: 'NSE:NIFTY_MICROCAP250/NSE:CNX500', label: 'Microcap 250 ÷ Nifty 500' },
  { symbol: 'NSE:NIFTYJR/NSE:CNX500', label: 'Next 50 ÷ Nifty 500' },
]

export function CapTierRSCharts() {
  return (
    <section className="px-8 py-10 border-b border-paper-rule" aria-label="Cap-tier relative strength">
      <div className="mb-5">
        <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Cap-tier relative strength</h2>
        <p className="font-sans text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
          Each tier index ÷ Nifty 500 — a rising line = the tier is outperforming the broad market.
          Live TradingView ratio charts (weekly; switch interval in-chart).
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {TIERS.map(t => (
          <TVRatioChart key={t.symbol} symbol={t.symbol} title={t.label} height={260} interval="W" />
        ))}
      </div>
    </section>
  )
}
