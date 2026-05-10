'use client'
import type { StockRow } from '@/lib/queries/sector-deep-dive'

type GateDef = {
  key: keyof StockRow
  label: string
  desc: string
}

const GATES: GateDef[] = [
  { key: 'market_gate',    label: 'Market',    desc: 'Market regime is constructive (Risk-On / Neutral)' },
  { key: 'sector_gate',    label: 'Sector',    desc: 'Sector is Overweight or Neutral' },
  { key: 'strength_gate',  label: 'Strength',  desc: 'Stock RS state is Leader, Strong, or Emerging' },
  { key: 'direction_gate', label: 'Direction', desc: 'Momentum state is Accelerating or Improving' },
  { key: 'risk_gate',      label: 'Risk',      desc: 'Risk state is not High or Below Trend' },
  { key: 'volume_gate',    label: 'Volume',    desc: 'Volume state shows Accumulation or Steady-Buying' },
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
                    <span className="text-ink-secondary">{label} Gate</span>
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
            <div className="flex items-center justify-between font-sans text-[10px] pt-1 border-t border-paper-rule">
              <span className="text-ink-primary font-semibold">Investable</span>
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
            desc="Stock is above 30-week MA with positive slope — Stage 2 uptrend per Weinstein methodology"
            bullThreshold={15}
          />

          {/* EMA at 20d high */}
          <SignalRow
            label="EMA at 20d High"
            count={emaHigh}
            total={total}
            desc="Stock's 10-day EMA is at its highest point in the last 20 days — momentum extending"
            bullThreshold={20}
          />

          {/* Index membership */}
          <div className="pt-2 border-t border-paper-rule space-y-1.5">
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">Index Coverage</div>
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
