'use client'
// TradesTable — the full transaction ledger with per-trade economics: execution
// cost, and on sells the FIFO realized P&L, holding days, STCG/LTCG bucket and
// provisional tax. Collapsed to a few line items by default; expand shows all
// fetched rows with a live/backtest switch. Every figure is a stored engine
// output (portfolio_trades) — nothing computed here beyond formatting.
import { useState } from 'react'
import type { TradeRow } from '@/lib/queries/portfolios'

const COLLAPSED_ROWS = 6

const inr = (v: number | null) =>
  v == null ? '—' : `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const inr2 = (v: number | null) =>
  v == null ? '—' : `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const tone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

const HEADS = ['Date', 'Instrument', 'Side', 'Qty', 'Price', 'Value', 'Cost', 'Realized P&L', 'Days', 'Bucket', 'Tax', 'Reason']

export function TradesTable({ trades }: { trades: TradeRow[] }) {
  const hasLive = trades.some((t) => t.runType === 'live')
  const [runType, setRunType] = useState<'live' | 'backtest'>(hasLive ? 'live' : 'backtest')
  const [expanded, setExpanded] = useState(false)

  const rows = trades.filter((t) => t.runType === runType)
  const shown = expanded ? rows : rows.slice(0, COLLAPSED_ROWS)

  return (
    <div>
      <div className="mb-2 flex items-center gap-2 px-1">
        {(['live', 'backtest'] as const).map((rt) => (
          <button
            key={rt}
            onClick={() => { setRunType(rt); setExpanded(false) }}
            className={`rounded-tile px-2.5 py-1 font-sans text-[11px] font-medium transition-colors ${
              runType === rt ? 'bg-surface-raised text-txt-1' : 'text-txt-3 hover:text-txt-1'
            }`}
          >
            {rt === 'live' ? `Live (${trades.filter((t) => t.runType === 'live').length})` : `Backtest (${trades.filter((t) => t.runType === 'backtest').length})`}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px]">
          <thead>
            <tr className="border-b border-edge-rule">
              {HEADS.map((h, i) => (
                <th key={h} className={`px-2.5 py-2 font-num text-[10px] uppercase tracking-wider text-txt-3 ${i <= 1 ? 'text-left' : 'text-right'}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan={HEADS.length} className="px-3 py-4 font-sans text-[12.5px] italic text-txt-3">No {runType} trades yet.</td></tr>
            )}
            {shown.map((t, i) => (
              <tr key={i} className="border-b border-edge-hair">
                <td className="px-2.5 py-1.5 font-num text-[11.5px] tabular-nums text-txt-2">{t.date}</td>
                <td className="px-2.5 py-1.5 font-num text-[12px] font-semibold tabular-nums text-txt-1">{t.symbol}</td>
                <td className={`px-2.5 py-1.5 text-right font-sans text-[10.5px] font-semibold uppercase ${t.side === 'buy' ? 'text-sig-pos' : 'text-sig-neg'}`}>{t.side}</td>
                <td className="px-2.5 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-2">{t.qty.toLocaleString('en-IN')}</td>
                <td className="px-2.5 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-2">{t.price.toFixed(2)}</td>
                <td className="px-2.5 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-1">{inr(t.value)}</td>
                <td className="px-2.5 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-3">{inr2(t.cost)}</td>
                <td className={`px-2.5 py-1.5 text-right font-num text-[11.5px] tabular-nums ${tone(t.realizedPnl)}`}>{t.side === 'sell' ? inr(t.realizedPnl) : '—'}</td>
                <td className="px-2.5 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-2">{t.holdingDays ?? '—'}</td>
                <td className="px-2.5 py-1.5 text-right font-num text-[10.5px] uppercase tabular-nums text-txt-3">{t.taxBucket ?? '—'}</td>
                <td className="px-2.5 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-2">{t.side === 'sell' ? inr2(t.tax) : '—'}</td>
                <td className="px-2.5 py-1.5 text-right font-sans text-[10.5px] text-txt-3">{t.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > COLLAPSED_ROWS && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="mt-2 font-sans text-[12px] font-medium text-brand hover:underline"
        >
          {expanded ? 'Collapse' : `Show all ${rows.length} trades`}
        </button>
      )}
    </div>
  )
}
