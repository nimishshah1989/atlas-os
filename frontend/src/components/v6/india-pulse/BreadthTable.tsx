// frontend/src/components/v6/india-pulse/BreadthTable.tsx
//
// Section 2 — Dense breadth table with 9 rows, delta columns, progress bars.
// Server component (no charts — sparklines omitted as they require time-series
// data not available in the breadth_table JSONB; marked as deferred).

import type { BreadthRow } from '@/lib/queries/v6/india_pulse'

type Props = {
  rows: BreadthRow[]
}

function fmtVal(row: BreadthRow): string {
  if (row.data_gap) return '—'
  if (row.today == null) return '—'
  const { metric, today } = row
  if (metric === 'pct_above_200dma' || metric === 'pct_above_50dma') {
    return `${today.toFixed(0)}%`
  }
  if (metric === 'ad_ratio') return today.toFixed(2)
  if (metric === 'mcclellan') return today >= 0 ? `+${today.toFixed(0)}` : `${today.toFixed(0)}`
  if (metric === 'ad_line') return today.toLocaleString('en-IN', { maximumFractionDigits: 0 })
  return today.toFixed(0)
}

function fmtDelta(val: number | null, metric: string): string {
  if (val == null) return '—'
  if (metric === 'ad_ratio') {
    const s = Math.abs(val).toFixed(2)
    return val >= 0 ? `+${s}` : `−${s}`
  }
  if (metric === 'ad_line') {
    const s = Math.abs(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })
    return val >= 0 ? `+${s}` : `−${s}`
  }
  const s = Math.abs(val).toFixed(1)
  return val >= 0 ? `+${s}` : `−${s}`
}

function deltaColor(val: number | null, metric: string): string {
  if (val == null) return 'text-ink-tertiary'
  // For lows count, rising is bad
  if (metric === 'new_52w_lows') {
    return val > 0 ? 'text-signal-neg font-semibold' : 'text-signal-pos font-semibold'
  }
  // For mcclellan oscillator, positive change = good
  return val > 0 ? 'text-signal-pos font-semibold' : val < 0 ? 'text-signal-neg font-semibold' : 'text-ink-tertiary'
}

function pbarColor(row: BreadthRow): string {
  if (row.today == null) return 'bg-signal-pos'
  const { metric, today } = row
  if (metric === 'pct_above_200dma' || metric === 'pct_above_50dma') {
    const pct = today // already 0-100 range from MV (rounded)
    return pct < 35 ? 'bg-signal-neg' : pct < 50 ? 'bg-signal-warn' : 'bg-signal-pos'
  }
  if (metric === 'ad_ratio') {
    return today < 0.7 ? 'bg-signal-neg' : today < 0.85 ? 'bg-signal-warn' : 'bg-signal-pos'
  }
  return 'bg-signal-warn'
}

function pbarWidth(row: BreadthRow): number {
  if (row.today == null || row.data_gap) return 0
  const { metric, today } = row
  if (metric === 'pct_above_200dma' || metric === 'pct_above_50dma') {
    return Math.min(100, Math.max(0, today))
  }
  if (metric === 'ad_ratio') {
    return Math.min(100, Math.max(0, today * 100))
  }
  if (metric === 'new_52w_highs') {
    return Math.min(100, Math.max(0, today * 2)) // scale: 50 highs = 100%
  }
  if (metric === 'new_52w_lows') {
    return Math.min(100, Math.max(0, today * 2))
  }
  return 0
}

function readsAs(row: BreadthRow): { text: string; tone: 'pos' | 'warn' | 'neg' | 'neutral' } {
  if (row.data_gap) return { text: 'Data not available in current pipeline.', tone: 'neutral' }
  if (row.today == null) return { text: 'No data for this period.', tone: 'neutral' }
  const { metric, today } = row
  switch (metric) {
    case 'pct_above_200dma':
      if (today < 35) return { text: 'Structural breadth impaired — less than a third above 200-DMA.', tone: 'neg' }
      if (today < 50) return { text: 'Below half-line. Less than half the Nifty 500 above 200-DMA.', tone: 'warn' }
      return { text: 'Majority of Nifty 500 above 200-DMA. Breadth healthy.', tone: 'pos' }
    case 'pct_above_50dma':
      if (today < 30) return { text: 'Short-term washout territory. Bottom decile historically.', tone: 'neg' }
      if (today < 50) return { text: 'Short-term breadth impaired. Most names below 50-DMA.', tone: 'warn' }
      return { text: 'Short-term breadth healthy. Majority above 50-DMA.', tone: 'pos' }
    case 'new_52w_highs':
      if (today < 10) return { text: 'Leadership stack thin. New highs concentrated in handful of names.', tone: 'neg' }
      return { text: 'New highs broadening. Leadership expanding.', tone: 'pos' }
    case 'new_52w_lows':
      if (today > 20) return { text: 'Lows expanding rapidly. Distribution signature.', tone: 'neg' }
      if (today > 5) return { text: 'Lows rising. Watch for acceleration.', tone: 'warn' }
      return { text: 'Few new lows. Market not in distribution mode.', tone: 'pos' }
    case 'ad_ratio':
      if (today < 0.7) return { text: 'Decliners winning. Below mid-cycle range.', tone: 'warn' }
      if (today < 1.0) return { text: 'Near parity. Advances matching declines.', tone: 'neutral' }
      return { text: 'Advances dominating. Broad participation.', tone: 'pos' }
    case 'mcclellan':
      if (today < -60) return { text: 'Deep oversold. Mean-reversion bounces historically common.', tone: 'neg' }
      if (today < 0) return { text: 'Negative. Net declines outpacing advances.', tone: 'warn' }
      return { text: 'Positive momentum in advance/decline flow.', tone: 'pos' }
    case 'ad_line':
      if (today < 0) return { text: 'YTD A-D negative. Rally carried by fewer than half the names.', tone: 'warn' }
      return { text: 'Cumulative A-D positive. Broad participation YTD.', tone: 'pos' }
    default:
      return { text: '—', tone: 'neutral' }
  }
}

const TONE_CLASS = {
  pos: 'text-signal-pos',
  warn: 'text-signal-warn',
  neg: 'text-signal-neg',
  neutral: 'text-ink-secondary',
}

const ROW_META: Record<string, string> = {
  pct_above_200dma: 'Nifty 500 · canonical breadth',
  pct_above_100dma: 'Nifty 500 · medium-term',
  pct_above_50dma: 'Nifty 500 · short-term',
  new_52w_highs: 'Count · Nifty 500',
  new_52w_lows: 'Count · Nifty 500',
  ad_ratio: '5-day rolling · Nifty 500',
  mcclellan: '19/39 EMA of net A/D',
  pct_4w_high: 'Nifty 500 · breadth thrust',
  ad_line: 'YTD running · Nifty 500',
}

export function BreadthTable({ rows }: Props) {
  if (rows.length === 0) {
    return <div className="text-sm text-ink-tertiary py-4">No breadth data available.</div>
  }

  return (
    <>
      <table className="w-full border-collapse text-[13px] bg-paper border border-paper-rule rounded-sm">
        <thead>
          <tr>
            <th className="text-left text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold px-3 py-2 border-b border-ink-rule bg-paper-deep w-[22%]">
              Measure
            </th>
            <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold px-3 py-2 border-b border-ink-rule bg-paper-deep w-[9%]">
              Today
            </th>
            <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold px-3 py-2 border-b border-ink-rule bg-paper-deep w-[8%]">
              Δ 1W
            </th>
            <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold px-3 py-2 border-b border-ink-rule bg-paper-deep w-[8%]">
              Δ 1M
            </th>
            <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold px-3 py-2 border-b border-ink-rule bg-paper-deep w-[8%]">
              Δ 3M
            </th>
            <th className="text-left text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold px-3 py-2 border-b border-ink-rule bg-paper-deep w-[18%]">
              Position
            </th>
            <th className="text-left text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold px-3 py-2 border-b border-ink-rule bg-paper-deep w-[27%]">
              Reads as
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => {
            const reads = readsAs(row)
            const showPbar = !row.data_gap &&
              ['pct_above_200dma', 'pct_above_50dma', 'ad_ratio', 'new_52w_highs', 'new_52w_lows'].includes(row.metric)

            return (
              <tr key={row.metric} className="border-b border-paper-rule last:border-b-0">
                <td className="px-3 py-2 text-ink-secondary">
                  <strong className="text-ink-primary text-[12.5px]">{row.label}</strong>
                  <span className="block text-[10px] text-ink-tertiary mt-0.5">
                    {ROW_META[row.metric] ?? ''}
                  </span>
                </td>
                <td className="text-right font-mono px-3 py-2 text-ink-secondary text-[12.5px]">
                  {fmtVal(row)}
                </td>
                <td className={`text-right font-mono px-3 py-2 text-[12.5px] ${deltaColor(row.delta_1w, row.metric)}`}>
                  {row.data_gap ? '—' : fmtDelta(row.delta_1w, row.metric)}
                </td>
                <td className={`text-right font-mono px-3 py-2 text-[12.5px] ${deltaColor(row.delta_1m, row.metric)}`}>
                  {row.data_gap ? '—' : fmtDelta(row.delta_1m, row.metric)}
                </td>
                <td className={`text-right font-mono px-3 py-2 text-[12.5px] ${deltaColor(row.delta_3m, row.metric)}`}>
                  {row.data_gap ? '—' : fmtDelta(row.delta_3m, row.metric)}
                </td>
                <td className="px-3 py-2">
                  {row.data_gap ? (
                    <span className="text-[11px] text-ink-tertiary italic">Pipeline gap</span>
                  ) : showPbar ? (
                    <div className="relative bg-paper-deep h-[6px] w-36 rounded-sm overflow-hidden inline-block align-middle">
                      <div
                        className={`h-full rounded-sm ${pbarColor(row)}`}
                        style={{ width: `${pbarWidth(row)}%` }}
                      />
                      {/* Threshold marker at 50% */}
                      {(row.metric === 'pct_above_200dma' || row.metric === 'pct_above_50dma') && (
                        <div className="absolute top-[-2px] bottom-[-2px] w-px bg-ink-tertiary" style={{ left: '50%' }} />
                      )}
                    </div>
                  ) : row.metric === 'mcclellan' ? (
                    <span className={`text-[11px] px-1.5 py-0.5 rounded-sm border font-semibold ${
                      (row.today ?? 0) < -60
                        ? 'bg-signal-neg/10 text-signal-neg border-signal-neg/30'
                        : (row.today ?? 0) < 0
                        ? 'bg-signal-warn/10 text-signal-warn border-signal-warn/30'
                        : 'bg-signal-pos/10 text-signal-pos border-signal-pos/30'
                    }`}>
                      {(row.today ?? 0) < -60 ? 'Oversold' : (row.today ?? 0) < 0 ? 'Negative' : 'Positive'}
                    </span>
                  ) : row.metric === 'ad_line' ? (
                    <span className={`text-[11px] px-1.5 py-0.5 rounded-sm border font-semibold ${
                      (row.today ?? 0) < 0
                        ? 'bg-signal-warn/10 text-signal-warn border-signal-warn/30'
                        : 'bg-signal-pos/10 text-signal-pos border-signal-pos/30'
                    }`}>
                      {(row.today ?? 0) < 0 ? 'Negative slope' : 'Positive slope'}
                    </span>
                  ) : (
                    <span className="text-ink-tertiary">—</span>
                  )}
                </td>
                <td className={`px-3 py-2 text-[11.5px] font-medium leading-[1.35] max-w-[220px] ${TONE_CLASS[reads.tone]}`}>
                  {reads.text}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="mt-3 text-[11px] text-ink-tertiary leading-[1.5]">
        <strong className="text-ink-secondary">Reading the table:</strong> Δ columns are the change in the metric vs that point in time —
        in <span className="font-mono">pp</span> for % metrics, in <span className="font-mono">count</span> for highs/lows/A-D.
        The Position column shows where today's reading sits; the threshold tick is at the regime-neutral level.
        Rows marked &ldquo;Pipeline gap&rdquo; require additional data sources not yet ingested.{' '}
        <em>Row sparklines: Pipeline gap — coming with next ingest.</em>
      </p>
    </>
  )
}
