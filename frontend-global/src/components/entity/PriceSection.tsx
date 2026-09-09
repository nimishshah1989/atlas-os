'use client'
// src/components/entity/PriceSection.tsx — what the instrument has actually done, on the bars the
// spine holds. This replaces three "arrives with the price spine" placeholder tiles that were
// still on the live detail page after 7.8 million bars and 4.4 million technical rows had landed:
// the data was there and the page was describing it instead of drawing it.
//
// TWO CHARTS, NOT ONE DUAL-AXIS CHART.
//   Price      close_adj with its own EMA 21/50/200. One scale, all dollars, and the averages are
//              computed on exactly the series they are drawn over (compute_technicals.py runs them
//              on close_adj) — an EMA-200 over close_tr would be two lines pretending to be one.
//   Against    both indexed to 100 at the window's first session, on close_tr. Drawing SPY's
//   SPY        dollar close beside a $40 fund puts the fund on the floor and compares nothing;
//              rebasing asks "what did a dollar do in each", which is the only question that
//              survives two different prices.
//
// THE RANGE BUTTONS COST NOTHING. The server sends five years once and each range is a slice of
// that same array, so switching is instant and the page makes one query, not six.
import { useMemo, useState } from 'react'
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'
import { Section } from '@/components/ui/Section'
import { formatIsoDate } from '@/lib/format'
import type { InstrumentSeries } from '@/lib/queries/series'
import { DEFAULT_RANGE, lastSessions, RANGES, rebase, type RangeKey } from '@/lib/series'

const line = (rows: readonly { date: string; value: string | null }[]) =>
  rows.flatMap((r) => {
    const v = r.value == null || r.value === '' ? null : Number(r.value)
    return v == null || !Number.isFinite(v) ? [] : [{ time: r.date, value: v }]
  })

export function PriceSection({ series, symbol }: { series: InstrumentSeries; symbol: string }) {
  const [range, setRange] = useState<RangeKey>(DEFAULT_RANGE)

  const window = useMemo(() => {
    const sessions = RANGES.find((r) => r.key === range)?.sessions ?? Number.POSITIVE_INFINITY
    return lastSessions(series.points, sessions)
  }, [series.points, range])

  const price: ChartSeries[] = useMemo(() => {
    if (window.length === 0) return []
    const out: ChartSeries[] = [
      { name: symbol, data: line(window.map((p) => ({ date: p.date, value: p.close_adj }))), color: 'accent', lineWidth: 2 },
    ]
    // An average only joins the chart if the instrument HAS one. A fund six months old has no
    // 200-day EMA, and a legend entry for an empty line is a promise the data does not keep.
    const emas = [
      { name: 'EMA 21', key: 'ema_21' as const, color: 'pos' as const },
      { name: 'EMA 50', key: 'ema_50' as const, color: 'warn' as const },
      { name: 'EMA 200', key: 'ema_200' as const, color: 'neg' as const },
    ]
    for (const e of emas) {
      const data = line(window.map((p) => ({ date: p.date, value: p[e.key] })))
      if (data.length > 0) out.push({ name: e.name, data, color: e.color, lineWidth: 1 })
    }
    return out
  }, [window, symbol])

  const growth: ChartSeries[] = useMemo(() => {
    if (window.length === 0) return []
    const mine = rebase(window.map((p) => ({ date: p.date, value: p.close_tr })))
    if (mine.length === 0) return []
    const out: ChartSeries[] = [{ name: symbol, data: mine.map((p) => ({ time: p.date, value: p.value })), color: 'accent', lineWidth: 2 }]
    if (series.benchmark.length > 0) {
      const from = window[0].date
      const to = window[window.length - 1].date
      const spy = rebase(
        series.benchmark.filter((b) => b.date >= from && b.date <= to).map((b) => ({ date: b.date, value: b.close_tr })),
      )
      if (spy.length > 0) out.push({ name: 'SPY', data: spy.map((p) => ({ time: p.date, value: p.value })), color: 'ink', lineWidth: 1 })
    }
    return out
  }, [window, series.benchmark, symbol])

  if (series.points.length === 0) {
    return (
      <Section title="Price" note="ohlcv_daily">
        <p className="panel px-4 py-3 text-body text-ink-2">
          The price spine holds no bars for {symbol}. Nothing is drawn rather than a chart of
          nothing.
        </p>
      </Section>
    )
  }

  const first = window[0]?.date
  const last = window[window.length - 1]?.date
  const note = first && last ? `${formatIsoDate(first)} to ${formatIsoDate(last)}, ${window.length} sessions` : 'ohlcv_daily'

  return (
    <Section
      title="Price"
      note={note}
      aside={
        <div className="seg" role="group" aria-label="Chart range">
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              className={`text-meta${range === r.key ? ' on' : ''}`}
              aria-pressed={range === r.key}
              onClick={() => setRange(r.key)}
            >
              {r.label}
            </button>
          ))}
        </div>
      }
    >
      <div className="panel px-2 py-2">
        <AtlasLightweightChart series={price} height={300} />
        <p className="px-2 pt-1 text-meta text-ink-3">
          Split-adjusted close with its exponential moving averages — the same series the averages
          are computed on.
        </p>
      </div>

      {growth.length > 0 && (
        <div className="panel mt-4 px-2 py-2">
          <AtlasLightweightChart series={growth} height={220} />
          <p className="px-2 pt-1 text-meta text-ink-3">
            {series.benchmark.length > 0 ? `${symbol} against SPY, ` : ''}both worth 100 at the start
            of the window, on total-return closes — dividends included.
          </p>
        </div>
      )}
    </Section>
  )
}
