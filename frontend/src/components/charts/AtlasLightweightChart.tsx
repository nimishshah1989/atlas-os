'use client'

// AtlasLightweightChart — universal time-series chart for Atlas v6.
//
// Wraps TradingView Lightweight Charts (Apache 2.0). One adapter, many uses:
// price + EMA overlay, breadth history with rolling MAs, regime classifier
// input panels, conviction trajectories, drift Z-scores, etc.
//
// Design goals:
//  - Drop in any number of named series; chart resizes to container width.
//  - Auto-compute EMA overlays so callers pass raw data only.
//  - Atlas aesthetic (paper bg, ink text, teal/signal-pos/neg/warn series).
//  - Server-component-safe: this file is the ONLY client component; you can
//    import it from a server-rendered page and pass `series` as a server
//    prop. The chart engine itself is client-mounted (TV requires a DOM).
//  - Honest about LC limitations: line, area, candlestick, histogram — only.
//    XY scatter, bubble, RRG, grid heatmaps still need Recharts/custom.
//
// Spec context:
//  - Pilot lands on the regime page "How we got here" panel as 4 small-
//    multiples for the regime classifier inputs (smallcap_rs_z,
//    breadth_pct_above_200dma, vix_percentile, cross_sectional_dispersion).
//  - Same component re-used at full size for index price + EMAs, ETF / fund
//    NAV charts, sector RS, etc.
//
// Phase 1 scope (this commit):
//  - Line series with EMA overlays (ema20, ema50, ema200)
//  - One y-axis, time x-axis (epoch seconds)
//  - Atlas theme (paper-soft bg, ink axis, teal default series)
//  - Compact (sparkline) and full modes
//  - Title + asOf + yLabel
//
// NOT IN SCOPE Phase 1 (add later as needed):
//  - Candlestick / OHLC (drop in when a stock-detail chart needs it)
//  - Volume histogram pane
//  - Custom indicators panel (LC plugins)
//  - Mouse-over price label

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

// ── Public types ──────────────────────────────────────────────────────────

export type SeriesColor =
  | 'teal'    // accent — primary series, conviction-style
  | 'pos'    // signal-pos green — bullish overlay
  | 'neg'    // signal-neg red — bearish overlay
  | 'warn'  // signal-warn amber — caution
  | 'ink'    // ink-secondary — neutral / benchmark line

export type SeriesOverlay = 'ema20' | 'ema50' | 'ema200'

export interface ChartPoint {
  /** Epoch seconds OR ISO date string. Both accepted; LC handles conversion. */
  time: number | string
  value: number
}

export interface ChartSeries {
  /** Display name (tooltip + legend). */
  name: string
  /** Time-ordered points. Must be sorted ASC by time; LC throws otherwise. */
  data: ChartPoint[]
  /** Atlas semantic color (mapped to the design token in mountChart). */
  color?: SeriesColor
  /** Auto-computed EMA overlays drawn alongside the primary series. */
  overlays?: SeriesOverlay[]
  /** Line thickness in px. Default 2. */
  lineWidth?: 1 | 2 | 3 | 4
}

export interface AtlasLightweightChartProps {
  /** Series to draw. Array order = z-order (first = back, last = front). */
  series: ChartSeries[]
  /** Outer container height in px. Default 280 (compact: 140). */
  height?: number
  /** Y-axis label, shown above the chart (not on the axis itself — cleaner). */
  yLabel?: string
  /** Title shown above yLabel. */
  title?: string
  /** "As of YYYY-MM-DD" subtext. */
  asOf?: string
  /** Sparkline mode: tighter padding, smaller fonts, hidden axes. */
  compact?: boolean
  /** Show last-value label badge in the top-right. Default false. */
  showLastValue?: boolean
  /** Optional className to merge into the outer container. */
  className?: string
}

// ── Atlas theme tokens (resolved from globals.css design system) ──────────

const COLOR_MAP: Record<SeriesColor, string> = {
  teal:    '#1D9E75',   // accent
  pos:    '#2F6B43',   // signal-pos
  neg:    '#B0492C',   // signal-neg
  warn:   '#C68B2E',   // signal-warn
  ink:    '#57534A',   // ink-secondary
}

// Translucent overlay colours for EMA lines — same hue, lower opacity.
const OVERLAY_COLOR: Record<SeriesOverlay, string> = {
  ema20:  '#1D9E7588',  // teal 53%
  ema50:  '#2F6B4399',  // pos 60%
  ema200: '#B0492C99',  // neg 60%
}

const OVERLAY_PERIOD: Record<SeriesOverlay, number> = {
  ema20:  20,
  ema50:  50,
  ema200: 200,
}

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

// ── Time normaliser (LC accepts UTCTimestamp number or BusinessDay string) ─

function toLcTime(t: number | string): Time {
  // If it's already a number (epoch seconds), pass through.
  if (typeof t === 'number') return t as Time
  // ISO date → use the date string (LC accepts 'YYYY-MM-DD').
  // Trim time portion if present.
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

  // Mount + update effect. We tear down and rebuild on every props change for
  // simplicity; LC is fast enough that this is fine for the data volumes Atlas
  // works with (typically <1000 points per series).
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const options: DeepPartial<ChartOptions> = {
      width: el.clientWidth,
      height: compact ? height - 12 : height,
      layout: {
        background: { color: '#FAFAF8' },         // paper
        textColor: '#8A8578',                       // ink-tertiary
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: compact ? 10 : 11,
      },
      grid: {
        vertLines: { color: '#F4F2EC' },           // paper-soft
        horzLines: { color: '#F4F2EC' },
      },
      crosshair: {
        mode: 1, // magnet
        vertLine: { color: '#C9C5BA', width: 1, style: 3, labelBackgroundColor: '#2A2724' },
        horzLine: { color: '#C9C5BA', width: 1, style: 3, labelBackgroundColor: '#2A2724' },
      },
      timeScale: {
        borderColor: '#E5E2DA',                    // paper-rule
        rightOffset: 4,
        barSpacing: compact ? 4 : 6,
        visible: !compact,
      },
      rightPriceScale: {
        borderColor: '#E5E2DA',
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
      const semanticColor = COLOR_MAP[s.color ?? 'teal']
      const primary = chart.addSeries(LineSeries, {
        color: semanticColor,
        lineWidth: s.lineWidth ?? 2,
        priceLineVisible: false,
        lastValueVisible: showLastValue,
        title: s.name,
      })
      primary.setData(s.data.map(p => ({ time: toLcTime(p.time), value: p.value })))
      seriesRefsRef.current.push(primary)

      for (const overlayKey of s.overlays ?? []) {
        const ema = computeEma(s.data, OVERLAY_PERIOD[overlayKey])
        const overlay = chart.addSeries(LineSeries, {
          color: OVERLAY_COLOR[overlayKey],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: `${s.name} ${overlayKey.toUpperCase()}`,
        })
        overlay.setData(ema.map(p => ({ time: toLcTime(p.time), value: p.value })))
        seriesRefsRef.current.push(overlay)
      }
    }

    chart.timeScale().fitContent()

    // Resize observer — LC doesn't auto-resize.
    const ro = new ResizeObserver(entries => {
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
  }, [series, height, compact, showLastValue])

  const lastValue = series[0]?.data.at(-1)?.value
  const lastDelta = (() => {
    const arr = series[0]?.data
    if (!arr || arr.length < 2) return null
    const cur = arr.at(-1)!.value
    const prev = arr.at(-2)!.value
    return cur - prev
  })()

  return (
    <div className={`bg-paper border border-paper-rule rounded-sm ${className}`}>
      {(title || yLabel || asOf || (showLastValue && lastValue != null)) && (
        <div className="flex items-baseline justify-between gap-3 px-3 pt-2 pb-1.5">
          <div className="flex flex-col">
            {title && (
              <div className="font-serif text-[14px] text-ink-primary leading-tight">{title}</div>
            )}
            {yLabel && (
              <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider leading-tight mt-0.5">
                {yLabel}
              </div>
            )}
          </div>
          <div className="flex items-baseline gap-3">
            {showLastValue && lastValue != null && (
              <div className="flex items-baseline gap-1">
                <span className="font-mono text-[14px] font-semibold text-ink-primary tabular-nums">
                  {lastValue.toFixed(2)}
                </span>
                {lastDelta != null && (
                  <span className={`font-mono text-[10px] tabular-nums ${
                    lastDelta > 0 ? 'text-signal-pos' : lastDelta < 0 ? 'text-signal-neg' : 'text-ink-tertiary'
                  }`}>
                    {lastDelta > 0 ? '+' : ''}{lastDelta.toFixed(2)}
                  </span>
                )}
              </div>
            )}
            {asOf && (
              <span className="font-sans text-[10px] text-ink-tertiary">as of {asOf}</span>
            )}
          </div>
        </div>
      )}
      <div ref={containerRef} style={{ height }} className="w-full" />
    </div>
  )
}
