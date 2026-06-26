'use client'

// StocksBubble2x2 — the ONE strong 2×2 for the /stocks screener:
//   x = Strength (avg conviction decile) · y = Leadership (# of 4 lenses top-decile)
//   bubble SIZE = ~20-session liquidity (₹ Cr) · bubble COLOUR = leadership.
// Click a dot → /stocks/<symbol>. Theme-aware: colours come from useThemeTokens
// so the chart recolours live with the day/night toggle.
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts'
import { useRouter } from 'next/navigation'
import type { StockListRow } from '@/lib/queries/v6/stock_lens'
import { useThemeTokens } from '@/components/v4/ui/useThemeTokens'

type Pt = { x: number; y: number; z: number; symbol: string; lead: number; liq: number }

export function StocksBubble2x2({ stocks }: { stocks: StockListRow[] }) {
  const router = useRouter()
  const t = useThemeTokens()
  const leadColor = (lead: number) =>
    !t ? '#888888' : lead >= 3 ? t.pos : lead === 2 ? t.brand : lead === 1 ? t.warn : t.tick

  const scored = stocks.filter((s) => s.strength != null)
  // null liquidity → the dataset's smallest known value, so the bubble still renders
  // at the floor of the size scale rather than collapsing to nothing.
  const liqVals = scored.map((s) => s.liq_cr).filter((v): v is number => v != null)
  const liqFloor = liqVals.length ? Math.min(...liqVals) : 1

  const data: Pt[] = scored.map((s) => {
    const liq = s.liq_cr ?? liqFloor
    return { x: Math.round((s.strength as number) * 10) / 10, y: s.lead, z: liq, symbol: s.symbol, lead: s.lead, liq }
  })

  const grid = t?.grid ?? '#88888822'
  const tick = t?.tick ?? '#888888'
  const label = t?.label ?? '#888888'
  const ref = t?.rule ?? '#88888844'

  return (
    <div className="rounded-tile border border-edge-hair bg-surface-inset/50 p-3">
      <ResponsiveContainer width="100%" height={360}>
        <ScatterChart margin={{ top: 12, right: 16, bottom: 28, left: 8 }}>
          <CartesianGrid stroke={grid} />
          <XAxis type="number" dataKey="x" domain={[0.5, 10.5]} tick={{ fontSize: 10, fill: tick }}
            label={{ value: 'Strength (avg decile)', position: 'bottom', fontSize: 11, fill: label }} />
          <YAxis type="number" dataKey="y" domain={[-0.3, 4.3]} tick={{ fontSize: 10, fill: tick }}
            label={{ value: 'Leadership (# lenses)', angle: -90, position: 'insideLeft', fontSize: 11, fill: label }} />
          <ZAxis type="number" dataKey="z" range={[30, 400]} />
          <ReferenceLine x={5.5} stroke={ref} strokeDasharray="3 3" />
          <ReferenceLine y={2} stroke={ref} strokeDasharray="3 3" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as Pt
              return (
                <div className="rounded-tile border border-edge-rule bg-surface-raised px-2.5 py-1.5 font-num text-[11px] tabular-nums text-txt-1 shadow-panel">
                  {p.symbol} · Strength {p.x.toFixed(1)} / Lead {p.lead}/4 · ₹{Math.round(p.liq)}cr
                </div>
              )
            }} />
          <Scatter
            data={data}
            isAnimationActive={false}
            style={{ cursor: 'pointer' }}
            onClick={(node) => {
              const p = (node as { payload?: Pt }).payload
              if (p?.symbol) router.push('/stocks/' + p.symbol)
            }}
          >
            {data.map((p, i) => <Cell key={i} fill={leadColor(p.lead)} fillOpacity={0.85} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
