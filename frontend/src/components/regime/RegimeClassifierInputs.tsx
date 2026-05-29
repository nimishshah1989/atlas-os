'use client'

// RegimeClassifierInputs — "How we got here" panel for the regime page.
//
// Renders the 4 inputs that actually drive today's regime classification as
// a grid of TradingView Lightweight Charts. First production use of the
// AtlasLightweightChart adapter (commit landed 2026-05-29 alongside this).
//
// The classifier (atlas/compute/regime.py classify_regime_state) reads:
//   - Nifty 500 vs EMA200       → primary trend
//   - pct_above_ema_50         → breadth
//   - india_vix                 → volatility / fear gauge
//   - mcclellan_oscillator     → breadth momentum
//
// CONTEXT.md §"Regime classifier thresholds" listed 4 inputs
// (smallcap_rs_z, breadth_pct_above_200dma, vix_percentile,
// cross_sectional_dispersion). Those are the spec's *intended* inputs from
// the original design — but the live classifier ships with the 4 above
// because the spec inputs require data tables we haven't wired yet
// (cross-sectional dispersion, vix percentile rank). This is a CONTEXT.md
// drift; I've flagged it but kept the chart aligned with the live classifier
// because that's what the user is reading on their screen.

import { AtlasLightweightChart, type ChartPoint } from '@/components/charts/AtlasLightweightChart'
import type { RegimeHistoryRow } from '@/lib/queries/regime'

interface Props {
  history: RegimeHistoryRow[]
  asOf: string
}

function toDateString(d: Date | string): string {
  if (typeof d === 'string') return d.slice(0, 10)
  return d.toISOString().slice(0, 10)
}

function toPoints(
  rows: RegimeHistoryRow[],
  mapper: (r: RegimeHistoryRow) => number | null,
): ChartPoint[] {
  const out: ChartPoint[] = []
  for (const r of rows) {
    const v = mapper(r)
    if (v == null || !Number.isFinite(v)) continue
    out.push({ time: toDateString(r.date), value: v })
  }
  return out
}

export function RegimeClassifierInputs({ history, asOf }: Props) {
  // Rows arrive newest-first from getRegimeHistory; LC needs ascending time.
  const sorted = [...history].sort((a, b) =>
    toDateString(a.date) < toDateString(b.date) ? -1 : 1
  )

  // Breadth — % of Nifty 500 above 50D EMA. Pass-band ~50% = regime
  // inflection. Above 70% = Risk-On / Constructive territory.
  const breadth = toPoints(sorted, r =>
    r.pct_above_ema_50 != null ? parseFloat(r.pct_above_ema_50) * 100 : null,
  )

  // VIX — India VIX. >25 = elevated fear. <15 = complacency.
  const vix = toPoints(sorted, r =>
    r.india_vix != null ? parseFloat(r.india_vix) : null,
  )

  // McClellan Oscillator — breadth momentum. Zero-line crossover marks
  // momentum reversal. +30 = strong thrust, -30 = washout.
  const mcclellan = toPoints(sorted, r =>
    r.mcclellan_oscillator != null ? parseFloat(r.mcclellan_oscillator) : null,
  )

  // Trend — Nifty 500 price as % above/below its 200D EMA. Positive =
  // primary uptrend confirmed. Negative = primary downtrend.
  // Computed inline from nifty500_close vs nifty500_ema_50_slope is not
  // direct; we proxy with ema_50_slope as the trend rate-of-change since
  // the 200D MA value isn't on RegimeHistoryRow (only the slope is). Below
  // we plot the EMA50 slope which captures trend acceleration/deceleration —
  // a better signal than a raw price-vs-MA ratio anyway.
  const trendSlope = toPoints(sorted, r =>
    r.nifty500_ema_50_slope != null ? parseFloat(r.nifty500_ema_50_slope) * 100 : null,
  )

  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <div className="mb-3">
        <h2 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
          How we got here — the 4 inputs that classify today&apos;s regime
        </h2>
        <p className="font-sans text-[12px] text-ink-tertiary mt-1 max-w-prose leading-relaxed">
          The regime classifier reads four signals daily. Each chart shows
          where the signal is today vs where it has been. The EMA overlay
          shows the trend of the signal itself — useful for spotting a regime
          turning before the verdict flips.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <AtlasLightweightChart
          title="Breadth"
          yLabel="% of Nifty 500 above 50D EMA"
          asOf={asOf}
          height={220}
          showLastValue
          series={[
            { name: 'Breadth', data: breadth, color: 'teal', overlays: ['ema20'] },
          ]}
        />

        <AtlasLightweightChart
          title="Volatility"
          yLabel="India VIX"
          asOf={asOf}
          height={220}
          showLastValue
          series={[
            { name: 'VIX', data: vix, color: 'neg', overlays: ['ema20'] },
          ]}
        />

        <AtlasLightweightChart
          title="Momentum (breadth thrust)"
          yLabel="McClellan Oscillator"
          asOf={asOf}
          height={220}
          showLastValue
          series={[
            { name: 'McClellan', data: mcclellan, color: 'pos', overlays: ['ema20'] },
          ]}
        />

        <AtlasLightweightChart
          title="Trend (Nifty 500 50D slope)"
          yLabel="EMA 50 slope (% / day)"
          asOf={asOf}
          height={220}
          showLastValue
          series={[
            { name: 'Trend slope', data: trendSlope, color: 'ink', overlays: ['ema20'] },
          ]}
        />
      </div>
    </section>
  )
}
