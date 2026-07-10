'use client'

// SectorRSMomentumBubble — the sector's "master" RS × momentum map (stocks-only, phase 1).
//   x = relative strength (rs_3m), toggle to RS-vs-sector (rs_sector_3m)
//   y = RS momentum = rs_1m − rs_3m  (>0 → RS accelerating vs the longer window)
//   bubble SIZE = ~20-session liquidity (₹ Cr); null → dataset floor (still renders)
//   bubble COLOUR = RAG composite decile (t.decile ramp) — where the name ranks overall
// Same recharts scatter idiom as SectorStock2x2/StocksBubble2x2; theme-aware via useThemeTokens.
// Quadrant framing mirrors the RRG: x-divider on the cross-sectional MEDIAN (relative read),
// y-divider on 0 (momentum sign). Click a dot → /stocks/<symbol>.
import { useState } from 'react'
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts'
import { useRouter } from 'next/navigation'
import type { SectorStock } from '@/lib/queries/sector_lens'
import { useThemeTokens } from '@/components/ui/useThemeTokens'

type XKey = 'rs_3m' | 'rs_sector_3m'
export type RSMomPt = { x: number; y: number; z: number; symbol: string; d_composite: number | null; liq: number }

// Pure point-builder (the logic worth testing). A stock plots only if the active RS window
// AND both momentum inputs (rs_1m, rs_3m) are present — nothing is fabricated for a missing
// number (CLAUDE.md rule #0). Null liquidity floors to the dataset minimum so the bubble
// still renders at the smallest size rather than collapsing to nothing.
export function rsMomentumPoints(stocks: SectorStock[], xKey: XKey): RSMomPt[] {
  const eligible = stocks.filter((s) => s[xKey] != null && s.rs_1m != null && s.rs_3m != null)
  const liqVals = eligible.map((s) => s.liq_cr).filter((v): v is number => v != null)
  const liqFloor = liqVals.length ? Math.min(...liqVals) : 1
  return eligible.map((s) => {
    const liq = s.liq_cr ?? liqFloor
    return {
      x: s[xKey] as number,
      y: (s.rs_1m as number) - (s.rs_3m as number),
      z: liq,
      symbol: s.symbol,
      d_composite: s.d_composite,
      liq,
    }
  })
}

const median = (xs: number[]): number => {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]
}

const AXES: Record<XKey, { label: string; short: string }> = {
  rs_3m: { label: 'Relative strength — 3M vs Nifty 500', short: 'vs Nifty 500' },
  rs_sector_3m: { label: 'Relative strength — 3M vs sector', short: 'vs sector' },
}

export function SectorRSMomentumBubble({ stocks }: { stocks: SectorStock[] }) {
  const router = useRouter()
  const t = useThemeTokens()
  const [xKey, setXKey] = useState<XKey>('rs_3m')

  const data = rsMomentumPoints(stocks, xKey)
  const excluded = stocks.length - data.length

  const grid = t?.grid ?? '#88888822'
  const tick = t?.tick ?? '#888888'
  const label = t?.label ?? '#888888'
  const ref = t?.rule ?? '#88888844'
  const fill = (d: number | null) => (t ? t.decile(d) : '#888888')

  const xs = data.map((p) => p.x)
  const ys = data.map((p) => p.y)
  const pad = (lo: number, hi: number) => (hi - lo) * 0.08 || 1
  const xMid = median(xs)
  const xDom: [number, number] = xs.length ? [Math.min(...xs) - pad(Math.min(...xs), Math.max(...xs)), Math.max(...xs) + pad(Math.min(...xs), Math.max(...xs))] : [-1, 1]
  // 0-centred (momentum sign is the signal), but hug the real spread — RS momentum
  // is a difference of RS ratios and often sits within ±0.5, so a fixed ±1 floor
  // would flatten every dot into a central band.
  const yAbs = Math.max(0.05, ...ys.map((y) => Math.abs(y)))
  const yDom: [number, number] = [-yAbs * 1.15, yAbs * 1.15]

  return (
    <section className="px-8 py-10 border-b border-edge-hair" aria-label="Sector RS × momentum bubble">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-[28px] font-normal tracking-tight text-txt-1">
            RS × momentum map <span className="font-num text-[15px] text-txt-3">· {data.length} plotted</span>
          </h2>
          <p className="font-sans text-[13px] text-txt-3 max-w-[760px] leading-[1.45] mt-1">
            Each dot is a constituent. <strong className="text-txt-2">X</strong> = 3-month relative strength,
            <strong className="text-txt-2"> Y</strong> = RS momentum (1M − 3M RS; above 0 = RS accelerating).
            Bubble size = ~20-session liquidity; colour = RAG composite decile (red → green). Top-right =
            strong and still accelerating. Click a dot → that stock.
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-tile border border-edge-hair bg-surface-inset/50 p-0.5" role="group" aria-label="Relative-strength benchmark">
          {(Object.keys(AXES) as XKey[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setXKey(k)}
              aria-pressed={xKey === k}
              className={`font-num text-[11px] px-2.5 py-1 rounded-tile transition-colors ${xKey === k ? 'bg-surface-raised text-txt-1 shadow-panel' : 'text-txt-3 hover:text-txt-2'}`}
            >
              {AXES[k].short}
            </button>
          ))}
        </div>
      </div>
      <div className="rounded-tile border border-edge-hair bg-surface-inset/50 p-3">
        <ResponsiveContainer width="100%" height={420}>
          <ScatterChart margin={{ top: 12, right: 20, bottom: 30, left: 12 }}>
            <CartesianGrid stroke={grid} />
            <XAxis type="number" dataKey="x" domain={xDom} tick={{ fontSize: 10, fill: tick }}
              tickFormatter={(v: number) => v.toFixed(1)}
              label={{ value: AXES[xKey].label, position: 'bottom', fontSize: 11, fill: label }} />
            <YAxis type="number" dataKey="y" domain={yDom} tick={{ fontSize: 10, fill: tick }}
              tickFormatter={(v: number) => v.toFixed(1)}
              label={{ value: 'RS momentum (1M − 3M)', angle: -90, position: 'insideLeft', fontSize: 11, fill: label }} />
            <ZAxis type="number" dataKey="z" range={[40, 460]} />
            <ReferenceLine x={xMid} stroke={ref} strokeDasharray="3 3" />
            <ReferenceLine y={0} stroke={ref} strokeDasharray="3 3" />
            <Tooltip cursor={{ strokeDasharray: '3 3' }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const p = payload[0].payload as RSMomPt
                return (
                  <div className="rounded-tile border border-edge-rule bg-surface-raised px-2.5 py-1.5 font-num text-[11px] tabular-nums text-txt-1 shadow-panel">
                    {p.symbol} · RS {p.x.toFixed(1)} · mom {p.y >= 0 ? '+' : ''}{p.y.toFixed(1)} · D{p.d_composite ?? '–'} · ₹{Math.round(p.liq)}cr
                  </div>
                )
              }} />
            <Scatter
              data={data}
              isAnimationActive={false}
              style={{ cursor: 'pointer' }}
              onClick={(node) => {
                const p = (node as { payload?: RSMomPt }).payload
                if (p?.symbol) router.push('/stocks/' + p.symbol)
              }}
            >
              {data.map((p, i) => <Cell key={i} fill={fill(p.d_composite)} fillOpacity={0.85} />)}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      {excluded > 0 && (
        <p className="font-sans text-[11px] text-txt-3 mt-1.5 leading-[1.4]">
          {excluded} of {stocks.length} constituent{stocks.length === 1 ? '' : 's'} not plotted — missing {AXES[xKey].short} relative-strength or momentum history (not fabricated with a stand-in).
        </p>
      )}
    </section>
  )
}
