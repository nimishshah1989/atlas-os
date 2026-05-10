'use client'
import type { StockRow } from '@/lib/queries/sector-deep-dive'

type GateDef = {
  key: keyof StockRow
  label: string
  desc: string
}

const GATES: GateDef[] = [
  {
    key: 'market_gate',
    label: 'Market Gate',
    desc: 'Top-level filter: market regime must be Risk-On or Neutral. If the market is Risk-Off, no sector has a green light regardless of its own signals — this gate blocks all positions. Derived from the market regime model (Nifty 500 RS, breadth, and VIX). When this gate fails, wait for the regime to improve before considering any sector.',
  },
  {
    key: 'sector_gate',
    label: 'Sector Gate',
    desc: 'The sector itself must be Overweight or Neutral. Underweight/Avoid sectors fail this gate even if individual stocks look good — swimming against the sector current destroys alpha. This gate uses the sector state computed from bottom-up and top-down signals combined.',
  },
  {
    key: 'strength_gate',
    label: 'Strength Gate',
    desc: 'Stock RS state must be Leader, Strong, or Emerging. Weak/Laggard stocks fail even in strong sectors. RS state is a 7-level classification based on 3-month RS percentile vs Nifty 500. You want to own the sector leaders, not the sector laggards just because the sector is doing well.',
  },
  {
    key: 'direction_gate',
    label: 'Direction Gate',
    desc: 'Momentum state must be Accelerating or Improving — RS must be rising, not just high. A stock with great past RS that is now decelerating is a sell, not a buy. This gate ensures you are buying into improving relative strength, not chasing a peak.',
  },
  {
    key: 'risk_gate',
    label: 'Risk Gate',
    desc: 'Risk state must NOT be High or Below Trend. High-risk stocks are significantly overextended — the probability of mean reversion is elevated. Below Trend stocks are in a downtrend. Both are structurally unfavorable entry conditions regardless of the sector setup.',
  },
  {
    key: 'volume_gate',
    label: 'Volume Gate',
    desc: 'Volume state must be Accumulation or Steady-Buying. This ensures institutional buying is present — price gains with rising volume confirm real demand. Distribution or neutral volume on price gains is a red flag (price can be manufactured; volume cannot).',
  },
]

function pct(n: number, total: number) {
  return total === 0 ? 0 : Math.round((n / total) * 100)
}

export function SectorQualityPanel({ stocks }: { stocks: StockRow[] }) {
  if (stocks.length === 0) return null

  const total = stocks.length
  const investable = stocks.filter(s => s.is_investable === true).length
  const weinstein  = stocks.filter(s => s.weinstein_gate_pass === true).length
  const emaHigh    = stocks.filter(s => s.ema_10_at_20d_high === true).length

  const hasGateData = stocks.some(s => s.market_gate != null)

  return (
    <div className="space-y-4 pt-3 border-t border-paper-rule">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
        Quality &amp; Signal Funnel — {total} stocks
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        {/* Gate funnel */}
        {hasGateData && (
          <div className="space-y-2">
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-2">Investment Gate Funnel</div>
            {GATES.map(({ key, label, desc }) => {
              const passed = stocks.filter(s => s[key] === true).length
              const p = pct(passed, total)
              return (
                <div key={key} className="space-y-0.5" title={desc}>
                  <div className="flex items-center justify-between font-sans text-[10px]">
                    <span className="text-ink-secondary">{label}</span>
                    <span
                      className="font-mono font-semibold"
                      style={{ color: p >= 70 ? '#16a34a' : p >= 40 ? '#f59e0b' : '#ef4444' }}
                    >
                      {passed}/{total} · {p}%
                    </span>
                  </div>
                  <div className="h-1.5 bg-paper-rule rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${p}%`,
                        background: p >= 70 ? '#16a34a' : p >= 40 ? '#f59e0b' : '#ef4444',
                      }}
                    />
                  </div>
                </div>
              )
            })}
            <div className="flex items-center justify-between font-sans text-[10px] pt-1 border-t border-paper-rule" title="Stocks that pass ALL 6 gates simultaneously. These are the only stocks considered for new positions — every gate must pass for a stock to be actionable.">
              <span className="text-ink-primary font-semibold">Investable (all gates pass)</span>
              <span
                className="font-mono font-semibold"
                style={{ color: pct(investable, total) >= 20 ? '#16a34a' : '#f59e0b' }}
              >
                {investable}/{total} · {pct(investable, total)}%
              </span>
            </div>
          </div>
        )}

        {/* Signal callouts */}
        <div className="space-y-3">
          <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-2">Breakout Signals</div>

          {/* Weinstein gate */}
          <SignalRow
            label="Stage 2 Ready (Weinstein)"
            count={weinstein}
            total={total}
            desc="Stock is above its 30-week (150-day) MA with the MA sloping upward — Stan Weinstein's Stage 2 uptrend criteria. Stage 2 = the markup phase where institutional accumulation has turned into price appreciation. Most gains in a stock's lifecycle happen in Stage 2. Stocks in Stages 1, 3, or 4 are structurally less favorable."
            bullThreshold={15}
          />

          {/* EMA at 20d high */}
          <SignalRow
            label="EMA at 20d High"
            count={emaHigh}
            total={total}
            desc="Stock's 10-day EMA is at its highest point in the last 20 trading days (1 calendar month). This means short-term momentum is at a local peak — the EMA has been consistently rising, not just the price. Used as a breakout confirmation signal: if RS is strong AND the 10d EMA is making new highs, the stock is likely in a breakout phase, not just a bounce."
            bullThreshold={20}
          />

          {/* Index membership */}
          <div className="pt-2 border-t border-paper-rule space-y-1.5">
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider" title="Index membership of stocks in this sector. Nifty 50 = largest 50 stocks by free-float market cap. Nifty 100 = top 100. Nifty 500 = top 500. Higher index membership = more liquidity and institutional coverage.">Index Coverage</div>
            {[
              { label: 'Nifty 50',  count: stocks.filter(s => s.in_nifty_50).length },
              { label: 'Nifty 100', count: stocks.filter(s => s.in_nifty_100).length },
              { label: 'Nifty 500', count: stocks.filter(s => s.in_nifty_500).length },
            ].map(({ label, count }) => (
              <div key={label} className="flex items-center justify-between font-sans text-[10px]">
                <span className="text-ink-secondary">{label}</span>
                <span className="font-mono text-ink-primary">
                  {count} stock{count !== 1 ? 's' : ''}
                  <span className="text-ink-tertiary ml-1">({pct(count, total)}%)</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SignalRow({
  label,
  count,
  total,
  desc,
  bullThreshold,
}: {
  label: string
  count: number
  total: number
  desc: string
  bullThreshold: number
}) {
  const p = pct(count, total)
  const isBull = p >= bullThreshold
  return (
    <div className="space-y-0.5" title={desc}>
      <div className="flex items-center justify-between font-sans text-[10px]">
        <span className="text-ink-secondary">{label}</span>
        <span className="font-mono font-semibold" style={{ color: isBull ? '#16a34a' : '#94a3b8' }}>
          {count} · {p}%
        </span>
      </div>
      <div className="h-1 bg-paper-rule rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${p}%`, background: isBull ? '#16a34a' : '#94a3b8' }}
        />
      </div>
    </div>
  )
}
