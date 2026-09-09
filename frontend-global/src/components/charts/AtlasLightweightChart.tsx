'use client'
// src/components/charts/AtlasLightweightChart.tsx — the board's time-series chart, on TradingView
// Lightweight Charts (Apache 2.0). India's frontend/src/components/charts/AtlasLightweightChart.tsx
// reduced to what this board draws: named line series on one price scale, resized to its
// container, painted from the design tokens in globals.css and repainted when the rail flips
// html[data-theme]. The ONLY client component a basket page needs: a server page passes
// `series` as a prop.
import { useEffect, useRef, useState } from 'react'
import { createChart, LineSeries, type IChartApi, type Time } from 'lightweight-charts'

export type SeriesColor = 'accent' | 'ink' | 'pos' | 'neg' | 'warn'

export interface ChartPoint {
  /** An ISO date (YYYY-MM-DD) — a postgres `date` selected as text. */
  time: string
  value: number
}

export interface ChartSeries {
  name: string
  data: ChartPoint[]
  color?: SeriesColor
  lineWidth?: 1 | 2 | 3 | 4
}

const TOKEN: Record<SeriesColor, string> = {
  accent: '--color-accent',
  ink: '--color-ink-2',
  pos: '--color-pos',
  neg: '--color-neg',
  warn: '--color-warn',
}

/** The active value of a globals.css token — the light set, or the dark override when on. */
function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** The current theme, and a re-render whenever the rail toggles it. */
function useTheme(): string {
  const [theme, setTheme] = useState('')
  useEffect(() => {
    const el = document.documentElement
    setTheme(el.getAttribute('data-theme') ?? '')
    const mo = new MutationObserver(() => setTheme(el.getAttribute('data-theme') ?? ''))
    mo.observe(el, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return theme
}

export function AtlasLightweightChart({
  series,
  height = 280,
  precision = 2,
}: {
  series: ChartSeries[]
  height?: number
  /** Price-scale decimals (2 for money and growth-of-100). */
  precision?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const theme = useTheme()

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const chart = createChart(el, {
      width: el.clientWidth,
      height,
      layout: {
        background: { color: token('--color-panel') },
        textColor: token('--color-ink-2'),
        fontFamily: 'var(--font-instrument-sans), system-ui, sans-serif',
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { color: token('--color-hair') }, horzLines: { color: token('--color-hair') } },
      crosshair: { mode: 1 },
      timeScale: { borderColor: token('--color-rule'), rightOffset: 4 },
      rightPriceScale: { borderColor: token('--color-rule'), scaleMargins: { top: 0.1, bottom: 0.1 } },
    })
    chartRef.current = chart
    for (const s of series) {
      const line = chart.addSeries(LineSeries, {
        color: token(TOKEN[s.color ?? 'accent']),
        lineWidth: s.lineWidth ?? 2,
        priceLineVisible: false,
        lastValueVisible: true,
        title: s.name,
        priceFormat: { type: 'price', precision, minMove: 1 / 10 ** precision },
      })
      line.setData(s.data.map((p) => ({ time: p.time.slice(0, 10) as Time, value: p.value })))
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
    }
  }, [series, height, precision, theme])

  return <div ref={containerRef} style={{ height }} className="w-full" data-chart={series.map((s) => s.name).join('|')} />
}
