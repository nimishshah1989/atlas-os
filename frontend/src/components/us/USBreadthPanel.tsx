'use client'
import Link from 'next/link'
import type { USStockRow } from '@/lib/queries/us-stocks'

type Props = {
  stocks: USStockRow[]
}

type TileProps = {
  label: string
  value: number
  pct?: number
  valueColor?: string
  pctColor?: string
  href?: string
}

function StatTile({ label, value, pct, valueColor = 'text-ink-primary', pctColor, href }: TileProps) {
  const inner = (
    <>
      <span className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide leading-none">
        {label}
      </span>
      <div className="flex items-baseline gap-2 mt-1">
        <span className={`font-sans text-xl font-semibold tabular-nums ${valueColor}`}>
          {value}
        </span>
        {pct !== undefined && (
          <span className={`font-sans text-xs tabular-nums ${pctColor ?? 'text-ink-secondary'}`}>
            {pct}%
          </span>
        )}
      </div>
    </>
  )
  if (href) {
    return (
      <Link
        href={href}
        className="rounded border border-paper-rule px-4 py-3 min-w-[140px] flex flex-col gap-0.5 hover:border-teal/60 hover:bg-teal/5 transition-colors cursor-pointer"
      >
        {inner}
      </Link>
    )
  }
  return (
    <div className="rounded border border-paper-rule px-4 py-3 min-w-[140px] flex flex-col gap-0.5">
      {inner}
    </div>
  )
}

export function USBreadthPanel({ stocks }: Props) {
  const live         = stocks.filter(s => s.history_gate_pass && s.liquidity_gate_pass)
  const totalLive    = live.length
  const above30W     = live.filter(s => s.above_30w_ma === true).length
  const leaderStrong = live.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length
  const accel        = live.filter(
    s => s.momentum_state === 'Accelerating' || s.momentum_state === 'Improving',
  ).length
  const weinstein    = live.filter(s => s.weinstein_gate_pass === true).length

  const pct = (n: number) =>
    totalLive > 0 ? Math.round((n / totalLive) * 100) : 0

  return (
    <div className="px-6 py-4 border-b border-paper-rule flex flex-wrap gap-3">
      <StatTile
        label="Live Stocks"
        value={totalLive}
        href="/us?tab=Stocks&filter=investable"
      />
      <StatTile
        label="Above 30W MA"
        value={above30W}
        pct={pct(above30W)}
        valueColor="text-blue-700"
        pctColor="text-blue-500"
        href="/us?tab=Stocks&filter=above_30w"
      />
      <StatTile
        label="Leader / Strong"
        value={leaderStrong}
        pct={pct(leaderStrong)}
        valueColor="text-teal"
        pctColor="text-teal"
        href="/us?tab=Stocks&filter=leader_strong"
      />
      <StatTile
        label="Accel / Improving"
        value={accel}
        pct={pct(accel)}
        valueColor="text-signal-pos"
        pctColor="text-signal-pos"
        href="/us?tab=Stocks&filter=accel_improving"
      />
      <StatTile
        label="Weinstein Gate"
        value={weinstein}
        pct={pct(weinstein)}
        valueColor="text-purple-700"
        pctColor="text-purple-500"
      />
    </div>
  )
}
