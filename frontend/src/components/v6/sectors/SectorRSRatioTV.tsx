'use client'

// SectorRSRatioTV — the sector's relative strength (sector index ÷ Nifty 50) as a DIRECT
// TradingView Advanced-Chart ratio embed. Used on the v4 sector deep-dive (SectorDeepDiveV4).
// The flag-OFF legacy route keeps the Lightweight SectorRSRatioCharts unchanged.
// Zero Atlas data. Symbol from sectorTvSymbols (FM watchlist + derived). Daily/Weekly/Monthly
// switch in-chart, so this is one interactive chart rather than three static panels.
import { TVRatioChart } from '@/components/charts/TVRatioChart'
import { sectorRatioEmbedSymbol } from '@/lib/v6/sectorTvSymbols'

export function SectorRSRatioTV({ sectorName }: { sectorName: string }) {
  const symbol = sectorRatioEmbedSymbol(sectorName)
  if (!symbol) {
    return (
      <div className="bg-paper-soft border border-paper-rule rounded-[2px] p-4 text-center text-[12px] text-ink-tertiary">
        Relative-strength chart unavailable — no TradingView index symbol mapped for {sectorName}.
      </div>
    )
  }
  return (
    <TVRatioChart
      symbol={symbol}
      height={440}
      interval="W"
      subtitle="Sector index ÷ Nifty 50 — rising = outperforming. Switch Daily / Weekly / Monthly in-chart."
    />
  )
}
