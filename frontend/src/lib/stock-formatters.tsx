import type { ReactNode } from 'react'

const DEPLOY_MAX = 1.2

export function PosSizeBar({ value }: { value: string | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const n = parseFloat(value)
  const display = `${(n * 100).toFixed(0)}%`
  const widthPct = Math.min(100, (n / DEPLOY_MAX) * 100)
  const color = n >= 0.7 ? '#2F6B43' : n >= 0.35 ? '#1D9E75' : n > 0 ? '#94a3b8' : '#ef4444'
  return (
    <div className="flex items-center gap-2">
      <div className="w-12 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${widthPct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{display}</span>
    </div>
  )
}

export function RSPctileBar({ value }: { value: string | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const n = parseFloat(value)
  const display = (n * 100).toFixed(0)
  const color = n >= 0.7 ? '#2F6B43' : n >= 0.4 ? '#f59e0b' : '#ef4444'
  return (
    <div className="flex items-center gap-2 justify-end">
      <div className="w-10 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.round(n * 100)}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{display}</span>
    </div>
  )
}

export function StateChip({ rs, mom }: { rs: string | null; mom: string | null }) {
  if (!rs) return <span className="font-sans text-[10px] text-ink-tertiary">—</span>
  const isOver = rs === 'Overweight_RS'
  const tone = isOver
    ? mom === 'Improving' ? 'bg-signal-pos/15 text-signal-pos'
      : mom === 'Deteriorating' ? 'bg-signal-warn/15 text-signal-warn'
      : 'bg-teal/15 text-teal'
    : 'bg-signal-neg/15 text-signal-neg'
  const label = isOver
    ? mom === 'Improving' ? '↑ Strong'
      : mom === 'Deteriorating' ? '↓ Fading'
      : '→ Stable'
    : '↓ Weak'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${tone}`}>
      {label}
    </span>
  )
}

export function pct(v: string | null, digits = 1, signed = true): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  const sign = signed && n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(digits)}%`
}

export function pctColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  return parseFloat(v) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

export function interpretRSPctile(v: string | null): ReactNode {
  if (v == null) return <p>No RS percentile data available.</p>
  const n = parseFloat(v) * 100
  if (n >= 80) return (
    <>
      <p>RS percentile <span className="text-signal-pos font-semibold">{n.toFixed(0)}th</span> — top tier within sector group.</p>
      <p>Outperforming the vast majority of peers. Sustained above 80th pctile confirms a leadership position.</p>
    </>
  )
  if (n >= 60) return (
    <>
      <p>RS percentile <span className="text-signal-pos font-medium">{n.toFixed(0)}th</span> — above-average relative strength.</p>
      <p>Outperforming most peers. Not yet clear leadership — watch for a sustained break above 80th pctile.</p>
    </>
  )
  if (n >= 40) return (
    <>
      <p>RS percentile <span className="text-signal-warn font-medium">{n.toFixed(0)}th</span> — middle of the peer group.</p>
      <p>Performing in line with sector peers. Watch for a break above 60th pctile to confirm improving momentum.</p>
    </>
  )
  return (
    <>
      <p>RS percentile <span className="text-signal-neg font-semibold">{n.toFixed(0)}th</span> — underperforming sector peers.</p>
      <p>Capital rotating away from this stock. Below 40th pctile is an avoid zone for new entries.</p>
    </>
  )
}

export function interpretMomentumState(state: string | null): ReactNode {
  if (!state) return <p>No momentum data available.</p>
  if (state === 'Improving') return (
    <>
      <p><span className="text-signal-pos font-semibold">Improving momentum</span> — RS trend is accelerating upward.</p>
      <p>Strongest entry signal. Improving RS + high pctile = high-conviction setup.</p>
    </>
  )
  if (state === 'Deteriorating') return (
    <>
      <p><span className="text-signal-neg font-semibold">Deteriorating momentum</span> — RS trend is weakening.</p>
      <p>Fading strength. Existing positions: watch closely. New positions: wait for stabilization.</p>
    </>
  )
  return (
    <>
      <p><span className="text-ink-secondary font-medium">Stable momentum</span> — RS trend holding steady.</p>
      <p>No acceleration either way. Acceptable for existing positions; not a trigger for new entries on its own.</p>
    </>
  )
}

export function interpretWeinsteinGate(pass: boolean | null, ema20dHigh: boolean | null): ReactNode {
  if (pass == null) return <p>Weinstein gate data unavailable.</p>
  if (pass) return (
    <>
      <p><span className="text-signal-pos font-semibold">Weinstein stage: PASS</span> — stock is in a confirmed Stage 2 uptrend.</p>
      <p>Above the 30-week MA, trend confirmed.{ema20dHigh ? ' EMA at 20-day high adds momentum confirmation.' : ' Monitor EMA for further confirmation.'}</p>
    </>
  )
  return (
    <>
      <p><span className="text-signal-neg font-semibold">Weinstein stage: FAIL</span> — not in a confirmed uptrend.</p>
      <p>Below the 30-week MA or in Stage 3/4 distribution. Avoid new positions regardless of RS. Wait for a stage transition.</p>
    </>
  )
}

export function interpretEMARatio(v: string | null): ReactNode {
  if (v == null) return <p>No EMA ratio data available.</p>
  const n = parseFloat(v)
  if (n >= 1.05) return (
    <>
      <p>EMA ratio <span className="text-signal-pos font-semibold">{n.toFixed(3)}</span> — stock EMA is {((n - 1) * 100).toFixed(1)}% above the benchmark EMA.</p>
      <p>Strong trend alignment. The stock is leading the benchmark in momentum terms.</p>
    </>
  )
  if (n >= 0.98) return (
    <>
      <p>EMA ratio <span className="text-ink-secondary font-medium">{n.toFixed(3)}</span> — roughly at parity with the benchmark.</p>
      <p>Stock moving broadly with the benchmark. No strong momentum edge in either direction.</p>
    </>
  )
  return (
    <>
      <p>EMA ratio <span className="text-signal-neg font-semibold">{n.toFixed(3)}</span> — stock EMA is below the benchmark.</p>
      <p>Momentum lagging the index. Consistent with Underweight RS positioning — avoid accumulating.</p>
    </>
  )
}

export function interpret3MReturn(v: string | null): ReactNode {
  if (v == null) return <p>No return data available.</p>
  const n = parseFloat(v) * 100
  if (n >= 15) return (
    <>
      <p>3-month return of <span className="text-signal-pos font-semibold">+{n.toFixed(1)}%</span> — strong absolute return.</p>
      <p>Check RS to confirm this gain beats the market, not just moves with it.</p>
    </>
  )
  if (n >= 5) return (
    <>
      <p>3-month return of <span className="text-signal-pos font-medium">+{n.toFixed(1)}%</span> — moderate positive return.</p>
      <p>Stocks are moving up on average. Compare RS to judge whether this beats the market or merely tracks it.</p>
    </>
  )
  if (n >= -5) return (
    <>
      <p>3-month return of <span className="text-ink-secondary font-medium">{n.toFixed(1)}%</span> — roughly flat.</p>
      <p>Neither advanced nor declined meaningfully. Opportunity cost applies unless RS is positive.</p>
    </>
  )
  return (
    <>
      <p>3-month return of <span className="text-signal-neg font-semibold">{n.toFixed(1)}%</span> — negative absolute return.</p>
      <p>Stock has lost money in absolute terms over 3 months. Unless this is bottoming with improving RS, it warrants avoiding.</p>
    </>
  )
}
