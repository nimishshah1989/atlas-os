import type { ReactNode } from 'react'
import { CHART_COLORS } from '@/lib/chart-colors'

const DEPLOY_MAX = 1.2

export function PosSizeBar({ value }: { value: string | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const n = parseFloat(value)
  const display = `${(n * 100).toFixed(0)}%`
  const widthPct = Math.min(100, (n / DEPLOY_MAX) * 100)
  const color = n >= 0.7 ? CHART_COLORS.rsLeader : n >= 0.35 ? CHART_COLORS.rsStrong : n > 0 ? CHART_COLORS.inkTertiary : CHART_COLORS.rsWeak
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
  const color = n >= 0.7 ? CHART_COLORS.rsLeader : n >= 0.4 ? CHART_COLORS.rsConsolidating : CHART_COLORS.rsWeak
  return (
    <div className="flex items-center gap-2 justify-end">
      <div className="w-10 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.round(n * 100)}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{display}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Individual state chip components — 7-level RS, 5-level Momentum/Risk/Volume
// ---------------------------------------------------------------------------

const RS_STATE_STYLE: Record<string, string> = {
  Leader:        'bg-signal-pos/20 text-signal-pos',
  Strong:        'bg-signal-pos/10 text-signal-pos',
  Consolidating: 'bg-teal/15 text-teal',
  Emerging:      'bg-signal-warn/15 text-signal-warn',
  Average:       'bg-ink-tertiary/10 text-ink-secondary',
  Weak:          'bg-signal-neg/10 text-signal-neg',
  Laggard:       'bg-signal-neg/20 text-signal-neg',
}

const RS_STATE_LABEL: Record<string, string> = {
  Leader:        'Leader',
  Strong:        'Strong',
  Consolidating: 'Consol',
  Emerging:      'Emrg',
  Average:       'Avg',
  Weak:          'Weak',
  Laggard:       'Laggard',
}

const MOM_STATE_STYLE: Record<string, string> = {
  Accelerating:  'bg-signal-pos/20 text-signal-pos',
  Improving:     'bg-signal-pos/10 text-signal-pos',
  Flat:          'bg-ink-tertiary/10 text-ink-secondary',
  Deteriorating: 'bg-signal-neg/10 text-signal-neg',
  Collapsing:    'bg-signal-neg/20 text-signal-neg',
}

const MOM_STATE_LABEL: Record<string, string> = {
  Accelerating:  'Accel',
  Improving:     'Impr',
  Flat:          'Flat',
  Deteriorating: 'Det',
  Collapsing:    'Coll',
}

const RISK_STATE_STYLE: Record<string, string> = {
  Low:           'bg-signal-pos/10 text-signal-pos',
  Normal:        'bg-ink-tertiary/10 text-ink-secondary',
  Elevated:      'bg-signal-warn/15 text-signal-warn',
  High:          'bg-signal-neg/15 text-signal-neg',
  'Below Trend': 'bg-purple-100 text-purple-700',
}

const RISK_STATE_LABEL: Record<string, string> = {
  Low:           'Low',
  Normal:        'Norm',
  Elevated:      'Elev',
  High:          'High',
  'Below Trend': '↓ Trnd',
}

const VOL_STATE_STYLE: Record<string, string> = {
  Accumulation:        'bg-signal-pos/20 text-signal-pos',
  'Steady-Buying':     'bg-signal-pos/10 text-signal-pos',
  Neutral:             'bg-ink-tertiary/10 text-ink-secondary',
  Distribution:        'bg-signal-neg/10 text-signal-neg',
  'Heavy Distribution':'bg-signal-neg/20 text-signal-neg',
}

const VOL_STATE_LABEL: Record<string, string> = {
  Accumulation:        'Accum',
  'Steady-Buying':     'S-Buy',
  Neutral:             'Neut',
  Distribution:        'Dist',
  'Heavy Distribution':'H-Dist',
}

function StateTag({
  label,
  style,
  raw,
}: {
  label: string
  style: string
  raw: string | null
}) {
  if (!raw || raw.startsWith('INSUFFICIENT') || raw.startsWith('DISLOCATION') || raw.startsWith('ILLIQUID')) {
    return <span className="font-mono text-[10px] text-ink-tertiary">—</span>
  }
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${style}`}
      title={raw}
    >
      {label}
    </span>
  )
}

export function RSStateChip({ value }: { value: string | null }) {
  const style = value ? (RS_STATE_STYLE[value] ?? 'bg-ink-tertiary/10 text-ink-secondary') : ''
  const label = value ? (RS_STATE_LABEL[value] ?? value) : ''
  return <StateTag raw={value} label={label} style={style} />
}

export function MomentumChip({ value }: { value: string | null }) {
  const style = value ? (MOM_STATE_STYLE[value] ?? 'bg-ink-tertiary/10 text-ink-secondary') : ''
  const label = value ? (MOM_STATE_LABEL[value] ?? value) : ''
  return <StateTag raw={value} label={label} style={style} />
}

export function RiskChip({ value }: { value: string | null }) {
  const style = value ? (RISK_STATE_STYLE[value] ?? 'bg-ink-tertiary/10 text-ink-secondary') : ''
  const label = value ? (RISK_STATE_LABEL[value] ?? value) : ''
  return <StateTag raw={value} label={label} style={style} />
}

export function VolumeChip({ value }: { value: string | null }) {
  const style = value ? (VOL_STATE_STYLE[value] ?? 'bg-ink-tertiary/10 text-ink-secondary') : ''
  const label = value ? (VOL_STATE_LABEL[value] ?? value) : ''
  return <StateTag raw={value} label={label} style={style} />
}

// 4-chip horizontal strip for stocks
export function StateTuple4({
  rs,
  mom,
  risk,
  vol,
}: {
  rs: string | null
  mom: string | null
  risk: string | null
  vol: string | null
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <RSStateChip value={rs} />
      <MomentumChip value={mom} />
      <RiskChip value={risk} />
      <VolumeChip value={vol} />
    </span>
  )
}

// 3-chip horizontal strip for ETFs (no volume gate)
export function StateTuple3({
  rs,
  mom,
  risk,
}: {
  rs: string | null
  mom: string | null
  risk: string | null
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <RSStateChip value={rs} />
      <MomentumChip value={mom} />
      <RiskChip value={risk} />
    </span>
  )
}

// Legacy combined chip — updated to use 7-level RS state logic
export function StateChip({ rs, mom }: { rs: string | null; mom: string | null }) {
  if (!rs) return <span className="font-sans text-[10px] text-ink-tertiary">—</span>
  const isLeader = rs === 'Leader' || rs === 'Strong'
  const isWeak = rs === 'Weak' || rs === 'Laggard'
  let tone: string
  let label: string
  if (isLeader) {
    tone = mom === 'Improving' || mom === 'Accelerating'
      ? 'bg-signal-pos/15 text-signal-pos'
      : mom === 'Deteriorating' || mom === 'Collapsing'
      ? 'bg-signal-warn/15 text-signal-warn'
      : 'bg-teal/15 text-teal'
    label = mom === 'Improving' || mom === 'Accelerating' ? '↑ Strong'
      : mom === 'Deteriorating' || mom === 'Collapsing' ? '↓ Fading'
      : '→ Stable'
  } else if (isWeak) {
    tone = 'bg-signal-neg/15 text-signal-neg'
    label = '↓ Weak'
  } else {
    tone = 'bg-ink-tertiary/10 text-ink-secondary'
    label = rs === 'Consolidating' ? '→ Consol'
      : rs === 'Emerging' ? '↑ Emrg'
      : '→ Avg'
  }
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
  if (state === 'Accelerating') return (
    <>
      <p><span className="text-signal-pos font-semibold">Accelerating momentum</span> — RS trend at a 20-day high.</p>
      <p>Strongest signal. Stock is pulling away from peers with rising short-term momentum. High-conviction entry context.</p>
    </>
  )
  if (state === 'Improving') return (
    <>
      <p><span className="text-signal-pos font-semibold">Improving momentum</span> — RS trend is rising.</p>
      <p>Short-term EMA above 20d EMA. Improving RS + high pctile = high-conviction setup.</p>
    </>
  )
  if (state === 'Deteriorating') return (
    <>
      <p><span className="text-signal-neg font-semibold">Deteriorating momentum</span> — RS trend is weakening.</p>
      <p>Fading strength. Existing positions: watch closely. New positions: wait for stabilisation.</p>
    </>
  )
  if (state === 'Collapsing') return (
    <>
      <p><span className="text-signal-neg font-semibold">Collapsing momentum</span> — RS trend at a 20-day low.</p>
      <p>Momentum in freefall. Exit or avoid. Do not add to a collapsing name regardless of RS rank.</p>
    </>
  )
  return (
    <>
      <p><span className="text-ink-secondary font-medium">Flat momentum</span> — RS trend holding steady.</p>
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
  if (v == null) return <p>No EMA momentum data available.</p>
  const n = parseFloat(v)
  if (n >= 1.02) return (
    <>
      <p>EMA ratio <span className="text-signal-pos font-semibold">{n.toFixed(3)}</span> — short-term EMA is {((n - 1) * 100).toFixed(1)}% above the 20d EMA.</p>
      <p>Stock is trending up in the short term. EMA10 above EMA20 signals upward price momentum.</p>
    </>
  )
  if (n >= 0.98) return (
    <>
      <p>EMA ratio <span className="text-ink-secondary font-medium">{n.toFixed(3)}</span> — EMAs roughly at parity.</p>
      <p>No strong directional momentum. Stock moving sideways in the short term.</p>
    </>
  )
  return (
    <>
      <p>EMA ratio <span className="text-signal-neg font-semibold">{n.toFixed(3)}</span> — short-term EMA is below the 20d EMA.</p>
      <p>Short-term momentum is down. Consistent with Deteriorating momentum state — avoid accumulating.</p>
    </>
  )
}

export function interpretDrawdown(v: string | null): ReactNode {
  if (v == null) return <p>No drawdown data available.</p>
  const n = parseFloat(v) * 100
  if (n >= -5) return (
    <>
      <p>Drawdown <span className="text-signal-pos font-semibold">{n.toFixed(1)}%</span> — near 52-week peak.</p>
      <p>Stock is trading close to its annual high. Minimal drawdown is a sign of sustained buying pressure.</p>
    </>
  )
  if (n >= -15) return (
    <>
      <p>Drawdown <span className="text-signal-warn font-medium">{n.toFixed(1)}%</span> — moderate pullback from peak.</p>
      <p>Normal correction range. Whether this is buyable depends on RS and momentum trend — is it a healthy consolidation or the start of deterioration?</p>
    </>
  )
  if (n >= -30) return (
    <>
      <p>Drawdown <span className="text-signal-neg font-semibold">{n.toFixed(1)}%</span> — significant decline from peak.</p>
      <p>Stock has lost significant ground. Only investable if RS and momentum are turning around, not during the fall.</p>
    </>
  )
  return (
    <>
      <p>Drawdown <span className="text-signal-neg font-semibold">{n.toFixed(1)}%</span> — deep drawdown from 52-week peak.</p>
      <p>Capital destruction territory. Avoid unless there is a clear structural recovery thesis with RS turning positive.</p>
    </>
  )
}

export function interpretExtension(v: string | null): ReactNode {
  if (v == null) return <p>No extension data available.</p>
  const n = parseFloat(v) * 100
  if (n >= 20) return (
    <>
      <p>Extension <span className="text-signal-warn font-semibold">+{n.toFixed(1)}%</span> above 200D EMA — stretched.</p>
      <p>Stock is extended from its long-term mean. Chasing at these levels adds risk — wait for a pullback toward the EMA before adding.</p>
    </>
  )
  if (n >= 5) return (
    <>
      <p>Extension <span className="text-signal-pos font-medium">+{n.toFixed(1)}%</span> above 200D EMA — healthy uptrend.</p>
      <p>Above the long-term trend with reasonable distance. This is the normal zone for a Weinstein Stage 2 stock.</p>
    </>
  )
  if (n >= -5) return (
    <>
      <p>Extension <span className="text-ink-secondary font-medium">{n.toFixed(1)}%</span> — near 200D EMA.</p>
      <p>At a critical decision zone. A bounce here with improving RS could be a re-entry; a break below could signal a stage change.</p>
    </>
  )
  return (
    <>
      <p>Extension <span className="text-signal-neg font-semibold">{n.toFixed(1)}%</span> — below 200D EMA.</p>
      <p>Stock is in Stage 3 or Stage 4. The Weinstein gate fails here — not investable for new positions.</p>
    </>
  )
}

export function interpretVolumeRatio(v: string | null): ReactNode {
  if (v == null) return <p>No volume data available.</p>
  const n = parseFloat(v)
  if (n >= 2000000) return (
    <>
      <p>Average volume <span className="text-signal-pos font-semibold">{(n / 1000000).toFixed(1)}M shares</span> — high liquidity.</p>
      <p>Institutional-grade liquidity. Sufficient for significant position sizing without meaningful market impact.</p>
    </>
  )
  if (n >= 500000) return (
    <>
      <p>Average volume <span className="text-signal-pos font-medium">{(n / 1000).toFixed(0)}K shares</span> — adequate liquidity.</p>
      <p>Sufficient for retail-to-mid-size positions. Monitor for volume spikes that confirm accumulation.</p>
    </>
  )
  return (
    <>
      <p>Average volume <span className="text-signal-warn font-medium">{(n / 1000).toFixed(0)}K shares</span> — thin liquidity.</p>
      <p>Low-volume stock. Price can move sharply on moderate orders. Apply a liquidity discount to position sizing.</p>
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
