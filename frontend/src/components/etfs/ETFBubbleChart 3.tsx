'use client'
import { useState, useMemo } from 'react'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { ETFRow } from '@/lib/queries/etfs'
import { bubbleColor } from '@/lib/chart-colors'

type ThemeFilter = 'all' | 'Broad' | 'Sectoral'

const VOL_CAP = 55
const RET_CAP = 0.80

type BubblePoint = {
  x: number
  y: number
  z: number
  ticker: string
  name: string
  theme: string
  color: string
  rs_state: string | null
  mom_state: string | null
}

const quadLabel = (
  pos: 'tl' | 'tr' | 'bl' | 'br',
  title: string,
  sub: string,
  color: string,
) => ({
  value: `${title} · ${sub}`,
  position: pos === 'tl' ? 'insideTopLeft' : pos === 'tr' ? 'insideTopRight' : pos === 'bl' ? 'insideBottomLeft' : 'insideBottomRight',
  fontSize: 9,
  fill: color,
  dy: pos.startsWith('t') ? 6 : -4,
  dx: pos.endsWith('l') ? 6 : -6,
} as const)

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: BubblePoint }> }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-paper border border-paper-rule shadow-sm rounded-sm p-2 text-[11px] font-sans min-w-[140px]">
      <div className="font-semibold text-ink-primary">{d.ticker}</div>
      <div className="text-ink-secondary text-[10px] mb-1.5 truncate max-w-[160px]">{d.name}</div>
      <div className="flex justify-between gap-4 text-ink-secondary">
        <span>Vol</span>
        <span className="text-ink-primary font-mono">{d.x.toFixed(1)}%</span>
      </div>
      <div className="flex justify-between gap-4 text-ink-secondary">
        <span>3M Ret</span>
        <span className={`font-mono ${d.y >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
          {d.y >= 0 ? '+' : ''}{d.y.toFixed(1)}%
        </span>
      </div>
      <div className="flex justify-between gap-4 text-ink-secondary">
        <span>RS</span>
        <span className="text-ink-primary font-mono">{d.rs_state ?? '—'}</span>
      </div>
    </div>
  )
}

export function ETFBubbleChart({ etfs }: { etfs: ETFRow[] }) {
  const [themeFilter, setThemeFilter] = useState<ThemeFilter>('all')

  const filtered = useMemo(() => {
    if (themeFilter === 'all') return etfs
    return etfs.filter(e => e.theme === themeFilter)
  }, [etfs, themeFilter])

  const data = useMemo<BubblePoint[]>(() => {
    return filtered.flatMap(e => {
      const retRaw = e.ret_3m != null ? parseFloat(e.ret_3m) : null
      const volRaw = e.vol_63 != null ? parseFloat(e.vol_63) * 100 : null
      const rs = e.rs_pctile_3m != null ? parseFloat(e.rs_pctile_3m) : null

      if (retRaw == null || volRaw == null) return []
      if (Math.abs(retRaw) > RET_CAP || volRaw > VOL_CAP) return []

      const z = rs != null ? 12 + Math.round(rs * 280) : 40

      return [{
        x: volRaw,
        y: retRaw * 100,
        z,
        ticker: e.ticker,
        name: e.etf_name ?? e.ticker,
        theme: e.theme,
        color: bubbleColor(e.rs_state, e.momentum_state),
        rs_state: e.rs_state,
        mom_state: e.momentum_state,
      }]
    })
  }, [filtered])

  const [yMin, yMax] = useMemo(() => {
    if (data.length === 0) return [-30, 60]
    const ys = data.map(d => d.y)
    const lo = Math.min(...ys), hi = Math.max(...ys)
    const pad = Math.max((hi - lo) * 0.12, 8)
    return [
      Math.max(-60, Math.floor((lo - pad) / 10) * 10),
      Math.min(120, Math.ceil((hi + pad) / 10) * 10),
    ]
  }, [data])

  const volMedian = useMemo(() => {
    if (data.length === 0) return 25
    const xs = [...data.map(d => d.x)].sort((a, b) => a - b)
    const raw = xs[Math.floor(xs.length / 2)]
    return Math.round(raw / 5) * 5
  }, [data])

  const counts = useMemo(() => ({
    all: etfs.length,
    Broad: etfs.filter(e => e.theme === 'Broad').length,
    Sectoral: etfs.filter(e => e.theme === 'Sectoral').length,
  }), [etfs])

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      <div className="px-5 py-3 border-b border-paper-rule flex flex-wrap items-center gap-4">
        <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
          ETF Map
        </span>
        <div className="flex gap-1 ml-auto items-center">
          <span className="font-sans text-[10px] text-ink-tertiary mr-1">Theme:</span>
          {(['all', 'Broad', 'Sectoral'] as ThemeFilter[]).map(f => (
            <button key={f} type="button" onClick={() => setThemeFilter(f)}
              className={`px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium transition-colors ${
                themeFilter === f
                  ? 'bg-ink-secondary text-paper'
                  : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}>
              {f === 'all' ? 'All' : f} ({counts[f]})
            </button>
          ))}
        </div>
      </div>

      <div className="px-5 py-2 border-b border-paper-rule/40 bg-paper-rule/5">
        <p className="font-sans text-[11px] text-ink-secondary leading-relaxed">
          <span className="font-semibold">Risk vs Return:</span>{' '}
          X = annualized 63-day volatility · Y = 3M return · Bubble size = RS percentile. {data.length} ETFs plotted.
        </p>
      </div>

      <div className="px-2 py-4" style={{ height: 400 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 24, bottom: 42, left: 36 }}>
            <ReferenceArea
              x1={0} x2={volMedian} y1={0} y2={yMax}
              fill="#22c55e" fillOpacity={0.04}
              label={quadLabel('tl', 'Quality Uptrend', 'low vol · rising', '#22c55e')}
            />
            <ReferenceArea
              x1={volMedian} x2={VOL_CAP} y1={0} y2={yMax}
              fill="#f59e0b" fillOpacity={0.04}
              label={quadLabel('tr', 'High Beta', 'high vol · rising', '#f59e0b')}
            />
            <ReferenceArea
              x1={0} x2={volMedian} y1={yMin} y2={0}
              fill="#94a3b8" fillOpacity={0.04}
              label={quadLabel('bl', 'Quiet Drift', 'low vol · falling', '#94a3b8')}
            />
            <ReferenceArea
              x1={volMedian} x2={VOL_CAP} y1={yMin} y2={0}
              fill="#ef4444" fillOpacity={0.05}
              label={quadLabel('br', 'Danger Zone', 'high vol · falling', '#ef4444')}
            />

            <XAxis
              type="number"
              dataKey="x"
              domain={[0, VOL_CAP]}
              tickFormatter={v => `${v.toFixed(0)}%`}
              label={{ value: 'Annualized Volatility % (63-day) →', position: 'insideBottom', offset: -28, fontSize: 10, fill: '#94a3b8' }}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickCount={7}
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={[yMin, yMax]}
              tickFormatter={v => `${v >= 0 ? '+' : ''}${v.toFixed(0)}%`}
              label={{ value: '↑ 3M Return', angle: -90, position: 'insideLeft', offset: 14, fontSize: 10, fill: '#94a3b8' }}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickCount={6}
            />
            <ZAxis type="number" dataKey="z" range={[12, 320]} />
            <Tooltip content={<CustomTooltip />} cursor={false} />

            <ReferenceLine y={0} stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1} />
            <ReferenceLine x={volMedian} stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1} />

            <Scatter data={data} isAnimationActive={false}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.color} fillOpacity={0.75} stroke={d.color} strokeWidth={0.5} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="px-5 py-2.5 border-t border-paper-rule/40 flex flex-wrap gap-4 items-center">
        {[
          { color: '#2F6B43', label: 'Leader' },
          { color: '#1D9E75', label: 'Strong' },
          { color: '#25394A', label: 'Emerging' },
          { color: '#B8860B', label: 'Consolidating' },
          { color: '#8C8278', label: 'Average/Weak' },
        ].map(({ color, label }) => (
          <span key={label} className="flex items-center gap-1.5 font-sans text-[10px] text-ink-secondary">
            <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            {label}
          </span>
        ))}
        <span className="font-sans text-[10px] text-ink-tertiary ml-auto">Bubble size = RS percentile</span>
      </div>
    </div>
  )
}
