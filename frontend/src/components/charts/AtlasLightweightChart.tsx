'use client'

// AtlasLightweightChart — universal time-series chart for Atlas.
//
// Wraps TradingView Lightweight Charts (Apache 2.0). One adapter, many uses:
// price + EMA overlay, breadth history with rolling MAs, regime classifier
// input panels, conviction trajectories, drift Z-scores, etc.
//
// Theme: when the page carries the v4 day/night theme (data-theme on <html>,
// surfaced via useThemeTokens) the chart paints from the design tokens and
// recolours live on toggle. Off-theme (legacy / flag-off) it keeps the original
// paper/ink palette byte-for-byte.
//
//  - Drop in any number of named series; chart resizes to container width.
//  - Auto-compute EMA overlays so callers pass raw data only.
//  - Server-component-safe: this is the ONLY client component; import it from a
//    server-rendered page and pass `series` as a server prop.
//  - Honest about LC limitations: line, area, candlestick, histogram — only.
//    XY scatter, bubble, RRG, grid heatmaps still need Recharts/custom.

import { useEffect, useRef } from 'react'
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type DeepPartial,
  type ChartOptions,
  LineSeries,
} from 'lightweight-charts'
import { useThemeTokens } from '@/components/v4/ui/useThemeTokens'

// ── Public types ──────────────────────────────────────────────────────────

export type SeriesColor =
  | 'teal'    // accent — primary series, conviction-style
  | 'pos'    // signal-pos green — bullish overlay
  | 'neg'    // signal-neg red — bearish overlay
  | 'warn'  // signal-warn amber — caution
  | 'ink'    // neutral / benchmark line

export type SeriesOverlay = 'ema20' | 'ema50' | 'ema200'

export interface ChartPoint {
  /** Epoch seconds OR ISO date string. Both accepted; LC handles conversion. */
  time: number | string
  value: number
}

export interface ChartSeries {
  name: string
  data: ChartPoint[]
  color?: SeriesColor
  overlays?: SeriesOverlay[]
  lineWidth?: 1 | 2 | 3 | 4
}

export interface AtlasLightweightChartProps {
  series: ChartSeries[]
  height?: number
  yLabel?: string
  title?: string
  asOf?: string
  compact?: boolean
  showLastValue?: boolean
  className?: string
}

// ── Legacy (off-theme) palette — unchanged paper/ink ────────────────────────

const COLOR_MAP: Record<SeriesColor, string> = {
  teal: '#1D9E75',
  pos: '#2F6B43',
  neg: '#B0492C',
  warn: '#C68B2E',
  ink: '#57534A',
}
const OVERLAY_COLOR: Record<SeriesOverlay, string> = {
  ema20: '#1D9E7588',
  ema50: '#2F6B4399',
  ema200: '#B0492C99',
}
const OVERLAY_PERIOD: Record<SeriesOverlay, number> = { ema20: 20, ema50: 50, ema200: 200 }

// ── EMA computation (pure helper) ─────────────────────────────────────────

function computeEma(data: ChartPoint[], period: number): ChartPoint[] {
  if (data.length === 0) return []
  const k = 2 / (period + 1)
  let ema = data[0].value
  return data.map((p, i) => {
    if (i === 0) return { time: p.time, value: ema }
    ema = p.value * k + ema * (1 - k)
    return { time: p.time, value: ema }
  })
}

function toLcTime(t: number | string): Time {
  if (typeof t === 'number') return t as Time
  return t.slice(0, 10) as Time
}

// ── Component ─────────────────────────────────────────────────────────────

export function AtlasLightweightChart({
  series,
  height = 280,
  yLabel,
  title,
  asOf,
  compact = false,
  showLastValue = false,
  className = '',
}: AtlasLightweightChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRefsRef = useRef<ISeriesApi<'Line'>[]>([])
  const tk = useThemeTokens() // null off-theme → legacy palette

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    // theme-aware palette: tk present (v4 data-theme) → design tokens; else legacy paper.
    const bg = tk ? tk.panel : '#FAFAF8'
    const txt = tk ? tk.txt2 : '#8A8578'
    const gridC = tk ? tk.grid : '#F4F2EC'
    const border = tk ? tk.rule : '#E5E2DA'
    const cross = tk ? tk.txt3 : '#C9C5BA'
    const crossBg = tk ? tk.txt1 : '#2A2724'
    const seriesColor = (c?: SeriesColor): string =>
      tk ? ({ teal: tk.brand, pos: tk.pos, neg: tk.neg, warn: tk.warn, ink: tk.txt2 } as Record<SeriesColor, string>)[c ?? 'teal'] : COLOR_MAP[c ?? 'teal']
    const overlayColor = (k: SeriesOverlay): string =>
      tk ? ({ ema20: tk.brand, ema50: tk.warn, ema200: tk.txt3 } as Record<SeriesOverlay, string>)[k] : OVERLAY_COLOR[k]

    const options: DeepPartial<ChartOptions> = {
      width: el.clientWidth,
      height: compact ? height - 12 : height,
      layout: {
        background: { color: bg },
        textColor: txt,
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: compact ? 10 : 11,
      },
      grid: {
        vertLines: { color: gridC },
        horzLines: { color: gridC },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: cross, width: 1, style: 3, labelBackgroundColor: crossBg },
        horzLine: { color: cross, width: 1, style: 3, labelBackgroundColor: crossBg },
      },
      timeScale: {
        borderColor: border,
        rightOffset: 4,
        barSpacing: compact ? 4 : 6,
        visible: !compact,
      },
      rightPriceScale: {
        borderColor: border,
        scaleMargins: { top: 0.1, bottom: 0.1 },
        visible: !compact,
      },
      handleScroll: !compact,
      handleScale: !compact,
    }

    const chart = createChart(el, options)
    chartRef.current = chart
    seriesRefsRef.current = []

    for (const s of series) {
      const primary = chart.addSeries(LineSeries, {
        color: seriesColor(s.color),
        lineWidth: s.lineWidth ?? 2,
        priceLineVisible: false,
        lastValueVisible: showLastValue,
        title: s.name,
      })
      primary.setData(s.data.map((p) => ({ time: toLcTime(p.time), value: p.value })))
      seriesRefsRef.current.push(primary)

      for (const overlayKey of s.overlays ?? []) {
        const ema = computeEma(s.data, OVERLAY_PERIOD[overlayKey])
        const overlay = chart.addSeries(LineSeries, {
          color: overlayColor(overlayKey),
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: `${s.name} ${overlayKey.toUpperCase()}`,
        })
        overlay.setData(ema.map((p) => ({ time: toLcTime(p.time), value: p.value })))
        seriesRefsRef.current.push(overlay)
      }
    }

    chart.timeScale().fitContent()

    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w && chartRef.current) chartRef.current.applyOptions({ width: Math.floor(w) })
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRefsRef.current = []
    }
  }, [series, height, compact, showLastValue, tk])

  const lastValue = series[0]?.data.at(-1)?.value
  const lastDelta = (() => {
    const arr = series[0]?.data
    if (!arr || arr.length < 2) return null
    return arr.at(-1)!.value - arr.at(-2)!.value
  })()

  // themed vs legacy chrome classes (keeps off-theme byte-identical)
  const cardCls = tk ? 'bg-surface-panel border border-edge-hair rounded-tile' : 'bg-paper border border-paper-rule rounded-sm'
  const titleCls = tk ? 'font-display text-[14px] text-txt-1 leading-tight' : 'font-serif text-[14px] text-ink-primary leading-tight'
  const yLabelCls = tk ? 'font-sans text-[10px] text-txt-3 uppercase tracking-wider leading-tight mt-0.5' : 'font-sans text-[10px] text-ink-tertiary uppercase tracking-wider leading-tight mt-0.5'
  const lastValCls = tk ? 'font-num text-[14px] font-semibold text-txt-1 tabular-nums' : 'font-mono text-[14px] font-semibold text-ink-primary tabular-nums'
  const deltaCls = lastDelta != null && lastDelta > 0
    ? (tk ? 'text-sig-pos' : 'text-signal-pos')
    : lastDelta != null && lastDelta < 0
      ? (tk ? 'text-sig-neg' : 'text-signal-neg')
      : (tk ? 'text-txt-3' : 'text-ink-tertiary')
  const asOfCls = tk ? 'font-sans text-[10px] text-txt-3' : 'font-sans text-[10px] text-ink-tertiary'

  return (
    <div className={`${cardCls} ${className}`}>
      {(title || yLabel || asOf || (showLastValue && lastValue != null)) && (
        <div className="flex items-baseline justify-between gap-3 px-3 pt-2 pb-1.5">
          <div className="flex flex-col">
            {title && <div className={titleCls}>{title}</div>}
            {yLabel && <div className={yLabelCls}>{yLabel}</div>}
          </div>
          <div className="flex items-baseline gap-3">
            {showLastValue && lastValue != null && (
              <div className="flex items-baseline gap-1">
                <span className={lastValCls}>{lastValue.toFixed(2)}</span>
                {lastDelta != null && (
                  <span className={`font-num text-[10px] tabular-nums ${deltaCls}`}>
                    {lastDelta > 0 ? '+' : ''}{lastDelta.toFixed(2)}
                  </span>
                )}
              </div>
            )}
            {asOf && <span className={asOfCls}>as of {asOf}</span>}
          </div>
        </div>
      )}
      <div ref={containerRef} style={{ height }} className="w-full" />
    </div>
  )
}
