'use client'

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import type { RSRatiosData } from '@/lib/queries/v6/stock-detail'

interface RSConfirmationPanelProps {
  rsData: RSRatiosData | null
  symbol: string
}

const STATUS_META = {
  BREAKING_OUT:     { label: 'BREAKING OUT',     cls: 'bg-signal-pos text-white' },
  AT_RESISTANCE:    { label: 'AT RESISTANCE',    cls: 'bg-signal-warn text-white' },
  BELOW_RESISTANCE: { label: 'BELOW RESISTANCE', cls: 'bg-signal-neg text-white' },
} as const

function StatusBadge({ status }: { status: keyof typeof STATUS_META }) {
  const meta = STATUS_META[status]
  return <span className={`inline-block px-2 py-0.5 rounded-[2px] font-mono text-[10px] font-semibold tracking-wider ${meta.cls}`}>{meta.label}</span>
}

function RatioChart({ data, resistance, label }: { data: { date: string; ratio: number }[]; resistance: number; label: string }) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">{label}</p>
      <ResponsiveContainer width="100%" height={130}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="rgba(194,184,168,0.3)" strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#9A8F82' }} tickLine={false} interval="preserveStartEnd" tickFormatter={(d: string) => d.slice(5)} />
          <YAxis tick={{ fontSize: 9, fill: '#9A8F82' }} tickLine={false} width={44} tickFormatter={(v: number) => v.toFixed(3)} />
          <Tooltip formatter={(v: unknown) => [(v as number).toFixed(4), 'Ratio']} labelStyle={{ fontSize: 11 }} contentStyle={{ fontSize: 11 }} />
          <ReferenceLine y={resistance} stroke="#B8860B" strokeDasharray="4 2" strokeWidth={1.5} label={{ value: 'Resistance', position: 'insideTopRight', fontSize: 9, fill: '#B8860B' }} />
          <Line type="monotone" dataKey="ratio" stroke="#1D9E75" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function generateRSSynthesis(rsData: RSRatiosData): string {
  const sectorLabel = rsData.sector_index_code ?? 'sector index'
  const { vs_sector_status: ss, vs_nifty50_status: ns } = rsData
  if (ss === 'BREAKING_OUT' && ns === 'BREAKING_OUT') return `Both RS ratios are breaking out above resistance. Strong dual confirmation — full position entry supported.`
  if (ss === 'BREAKING_OUT') return `RS vs ${sectorLabel} confirmed above resistance. RS vs Nifty 50 still lagging — consider a partial position until the Nifty ratio confirms.`
  if (ns === 'BREAKING_OUT') return `RS vs Nifty 50 is breaking out but the sector ratio is still lagging. Monitor sector ratio for confirmation.`
  if (ss === 'AT_RESISTANCE' || ns === 'AT_RESISTANCE') return `One or both RS ratios are testing resistance. Watch for a confirmed close above before entering.`
  return `Both RS ratios remain below resistance. Wait for at least one ratio to break out before entering.`
}

export function RSConfirmationPanel({ rsData, symbol }: RSConfirmationPanelProps) {
  const hasSector = (rsData?.vs_sector?.length ?? 0) > 0
  const hasNifty = (rsData?.vs_nifty50?.length ?? 0) > 0

  if (!rsData || (!hasSector && !hasNifty)) {
    return (
      <section className="px-6 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">Relative Strength Confirmation</p>
        <p className="font-sans text-sm text-ink-3">RS ratio data unavailable for {symbol} — insufficient overlapping price history vs its sector index and Nifty 50.</p>
      </section>
    )
  }

  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">Relative Strength Confirmation — Is the move confirmed?</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
        {hasSector && (
          <div className="bg-paper border border-paper-rule rounded p-4">
            <RatioChart data={rsData.vs_sector} resistance={rsData.vs_sector_resistance} label={`${symbol} ÷ ${rsData.sector_index_code}`} />
            <div className="mt-2"><StatusBadge status={rsData.vs_sector_status} /></div>
          </div>
        )}
        {hasNifty && (
          <div className="bg-paper border border-paper-rule rounded p-4">
            <RatioChart data={rsData.vs_nifty50} resistance={rsData.vs_nifty50_resistance} label={`${symbol} ÷ Nifty 50`} />
            <div className="mt-2"><StatusBadge status={rsData.vs_nifty50_status} /></div>
          </div>
        )}
      </div>
      <div className="bg-paper-deep border border-paper-rule rounded p-4">
        <p className="font-mono text-[10px] text-teal uppercase tracking-wider mb-2">Entry Timing</p>
        <p className="font-sans text-sm text-ink leading-relaxed">{generateRSSynthesis(rsData)}</p>
      </div>
    </section>
  )
}
