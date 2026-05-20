'use client'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import type { ColumnDef } from '@/components/ui/ColumnToggle'

export const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
export const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
export const RISK_ORDER = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend']
export const VOL_ORDER = ['Accumulation', 'Steady-Buying', 'Neutral', 'Distribution', 'Heavy Distribution']

export type SortKey =
  | 'symbol' | 'sector' | 'rs_pctile_3m' | 'cap_rank'
  | 'ret_1m' | 'ret_3m' | 'ret_6m'
  | 'rs_state' | 'momentum_state' | 'risk_state' | 'volume_state'
  | 'within_state_rank'

export type FilterChip = 'all' | 'n50' | 'n100' | 'n500' | 'investable' | 'leader' | 'accel'

export const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',        label: 'All' },
  { key: 'n50',        label: 'Nifty 50' },
  { key: 'n100',       label: 'Nifty 100' },
  { key: 'n500',       label: 'Nifty 500' },
  { key: 'investable', label: 'Investable' },
  { key: 'leader',     label: 'Leader/Strong' },
  { key: 'accel',      label: 'Accelerating' },
]

// Optional columns. 1W, 6M, 12M visible by default.
export const OPTIONAL_COLS: ColumnDef[] = [
  { key: 'conviction',      label: 'Conviction',  defaultVisible: true },
  { key: 'quality',         label: 'Grade',       defaultVisible: true },
  { key: 'ret_1d',          label: '1D',          defaultVisible: false },
  { key: 'ret_1w',          label: '1W',          defaultVisible: true },
  { key: 'ret_6m',          label: '6M',          defaultVisible: true },
  { key: 'ret_12m',         label: '12M',         defaultVisible: true },
  { key: 'rs_pctile_1w',   label: 'RS 1W',       defaultVisible: false },
  { key: 'rs_pctile_1m',   label: 'RS 1M',       defaultVisible: false },
  { key: 'extension_pct',  label: 'Ext %',       defaultVisible: false },
  { key: 'ema_20_ratio',   label: 'EMA20 %',    defaultVisible: false },
  { key: 'vol_63',         label: 'Vol (63D)',   defaultVisible: false },
  { key: 'vol_ratio_63',   label: 'Vol Ratio',   defaultVisible: false },
  { key: 'max_drawdown_252', label: 'Max DD',    defaultVisible: false },
  { key: 'drawdown',       label: 'Drawdown',    defaultVisible: false },
  { key: 'effort_ratio_63', label: 'Effort',     defaultVisible: false },
  { key: 'volume_expansion', label: 'Vol Exp',   defaultVisible: false },
  { key: 'ma_30w_slope_4w', label: '30W Slope',  defaultVisible: false },
  { key: 'days_in_state',  label: 'Days',        defaultVisible: false },
  { key: 'alpha_3m',       label: 'α 3M',        defaultVisible: false },
  { key: 'alpha_6m',       label: 'α 6M',        defaultVisible: false },
  { key: 'live_price',     label: 'Live ₹',      defaultVisible: false },
]

export const COL_STORAGE_KEY = 'atlas-stock-screener-cols'

// Always-visible columns: Symbol, Cap, Sector, RS State, Risk, 1M, 3M, RS Pctile = 8
// (Gates, Mom, Vol columns removed in Phase 8)
export const ALWAYS_VISIBLE_COL_COUNT = 8

export const GATE_LEGEND = [
  { key: 'H', field: 'history_gate_pass',   label: 'History',   desc: 'Stock has ≥6M of price history in our universe' },
  { key: 'L', field: 'liquidity_gate_pass', label: 'Liquidity', desc: 'Avg daily value traded meets minimum threshold' },
  { key: 'W', field: 'weinstein_gate_pass', label: 'Weinstein', desc: 'Price is in Weinstein Stage 2 (above rising 30W MA)' },
  { key: 'S', field: 'strength_gate',       label: 'Strength',  desc: 'RS State is Leader, Strong, or Emerging' },
  { key: 'D', field: 'direction_gate',      label: 'Direction', desc: 'Momentum is Accelerating or Improving' },
  { key: 'R', field: 'risk_gate',           label: 'Risk',      desc: 'Risk state is Low or Normal (not Elevated/High/Below Trend)' },
  { key: 'V', field: 'volume_gate',         label: 'Volume',    desc: 'Volume state is Accumulation or Steady-Buying' },
  { key: 'G', field: 'sector_gate',         label: 'Sector',    desc: 'Sector is not in avoid list (sector momentum is healthy)' },
  { key: 'M', field: 'market_gate',         label: 'Market',    desc: 'Market regime is Risk-On or Cautious (not Risk-Off)' },
]

// Returns true if the current wall-clock time is within NSE market hours (09:15–15:35 IST, Mon–Fri).
export function isMarketOpen(): boolean {
  const now = new Date()
  const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes()
  const istMinutes = utcMinutes + 330
  const dayOfWeek = new Date(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate() + Math.floor(istMinutes / 1440),
  ).getDay()
  if (dayOfWeek === 0 || dayOfWeek === 6) return false
  const istDayMinutes = istMinutes % 1440
  return istDayMinutes >= 555 && istDayMinutes <= 935
}

export function stateRank(order: string[], val: string | null): number {
  if (!val) return order.length
  const i = order.indexOf(val)
  return i === -1 ? order.length : i
}

export function capRank(s: StockRowWithSector): number {
  if (s.in_nifty_50) return 1
  if (s.in_nifty_100) return 2
  if (s.in_nifty_500) return 3
  return 4
}

// Safely read an optional field that may not exist on the row type.
export function optField(row: StockRowWithSector, key: string): unknown {
  return (row as unknown as Record<string, unknown>)[key]
}

export function optStr(row: StockRowWithSector, key: string): string | null {
  const v = optField(row, key)
  if (v == null) return null
  return typeof v === 'string' ? v : String(v)
}

export function optBool(row: StockRowWithSector, key: string): boolean | null {
  const v = optField(row, key)
  if (v === true || v === false) return v
  return null
}

export function optNum(row: StockRowWithSector, key: string): number | null {
  const v = optField(row, key)
  if (v == null) return null
  if (typeof v === 'number') return v
  if (typeof v === 'string') {
    const n = parseFloat(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

// Composite quality grade derived from RS state, momentum, risk, volume, stage, and RS pctile.
export function buildStockGrade(row: StockRowWithSector): { grade: string; color: string; score: number } {
  let score = 0
  const rsScore: Record<string, number>   = { Leader: 3, Strong: 2, Consolidating: 1, Emerging: 1, Average: 0, Weak: -1, Laggard: -2 }
  const momScore: Record<string, number>  = { Accelerating: 2, Improving: 1, Flat: 0, Deteriorating: -1, Collapsing: -2 }
  const riskScore: Record<string, number> = { Low: 1, Normal: 0, Elevated: -1, High: -2, 'Below Trend': -1 }
  const volScore: Record<string, number>  = { Accumulation: 2, 'Steady-Buying': 1, Neutral: 0, Distribution: -1, 'Heavy Distribution': -2 }
  score += rsScore[row.rs_state ?? ''] ?? 0
  score += momScore[row.momentum_state ?? ''] ?? 0
  score += riskScore[row.risk_state ?? ''] ?? 0
  score += volScore[row.volume_state ?? ''] ?? 0
  if (row.above_30w_ma === true) score += 1
  const p = row.rs_pctile_3m != null ? parseFloat(row.rs_pctile_3m) : null
  if (p != null) { if (p >= 0.75) score += 1; else if (p < 0.25) score -= 1 }
  if (score >= 5) return { grade: 'A', color: '#2F6B43', score }
  if (score >= 1) return { grade: 'B', color: '#d97706', score }
  return { grade: 'C', color: '#ef4444', score }
}

export function buildGradeTooltip(row: StockRowWithSector): string {
  const rsScore: Record<string, number>   = { Leader: 3, Strong: 2, Consolidating: 1, Emerging: 1, Average: 0, Weak: -1, Laggard: -2 }
  const momScore: Record<string, number>  = { Accelerating: 2, Improving: 1, Flat: 0, Deteriorating: -1, Collapsing: -2 }
  const riskScore: Record<string, number> = { Low: 1, Normal: 0, Elevated: -1, High: -2, 'Below Trend': -1 }
  const volScore: Record<string, number>  = { Accumulation: 2, 'Steady-Buying': 1, Neutral: 0, Distribution: -1, 'Heavy Distribution': -2 }
  const rs    = rsScore[row.rs_state ?? ''] ?? 0
  const mom   = momScore[row.momentum_state ?? ''] ?? 0
  const risk  = riskScore[row.risk_state ?? ''] ?? 0
  const vol   = volScore[row.volume_state ?? ''] ?? 0
  const stage = row.above_30w_ma === true ? 1 : 0
  const p = row.rs_pctile_3m != null ? parseFloat(row.rs_pctile_3m) : null
  const pctile = p != null ? (p >= 0.75 ? 1 : p < 0.25 ? -1 : 0) : 0
  const total  = rs + mom + risk + vol + stage + pctile
  const grade  = total >= 5 ? 'A' : total >= 1 ? 'B' : 'C'
  const s = (n: number) => n > 0 ? `+${n}` : `${n}`
  const pLabel = p != null ? `${Math.round(p * 100)}th%` : 'n/a'
  return [
    `Grade ${grade}  (composite score ${s(total)})`,
    `  RS State (${row.rs_state ?? '—'}):  ${s(rs)}`,
    `  Momentum (${row.momentum_state ?? '—'}):  ${s(mom)}`,
    `  Risk (${row.risk_state ?? '—'}):  ${s(risk)}`,
    `  Volume (${row.volume_state ?? '—'}):  ${s(vol)}`,
    `  Stage 2 (${row.above_30w_ma === true ? 'above 30W MA' : 'below 30W MA'}):  ${s(stage)}`,
    `  RS Percentile (${pLabel}):  ${s(pctile)}`,
    '',
    'A ≥5 = strong alignment across signals',
    'B 1–4 = mixed — some positive, some not',
    'C ≤0 = predominantly negative signals',
  ].join('\n')
}

// Deterministic signal string explaining the stock's classification.
export function buildStockSignal(row: StockRowWithSector): { compact: string; tooltip: string } {
  const parts: string[] = []
  const tip: string[] = []
  const p = row.rs_pctile_3m != null ? Math.round(parseFloat(row.rs_pctile_3m) * 100) : null
  if (p != null) { parts.push(`${p}th%`); tip.push(`RS Pctile (3M): ${p}th percentile`) }
  if (row.above_30w_ma === true)       { parts.push('Stage2');  tip.push('Stage 2: Above rising 30W MA ✓') }
  else if (row.above_30w_ma === false) { parts.push('BelowMA'); tip.push('Stage 2: Below 30W MA ✗') }
  const momShort: Record<string, string> = { Accelerating: 'Accel', Improving: 'Improv', Flat: 'Flat', Deteriorating: 'Detr', Collapsing: 'Coll' }
  if (row.momentum_state) { parts.push(momShort[row.momentum_state] ?? row.momentum_state); tip.push(`Momentum: ${row.momentum_state}`) }
  const volShort: Record<string, string> = { Accumulation: 'Accum', 'Steady-Buying': 'Steady', Distribution: 'Distr', 'Heavy Distribution': 'H.Distr' }
  if (row.volume_state && row.volume_state !== 'Neutral') { parts.push(volShort[row.volume_state] ?? row.volume_state); tip.push(`Volume: ${row.volume_state}`) }
  if (row.risk_state === 'High')     { parts.push('⚠Risk');  tip.push('Risk: HIGH — risk_gate fails → position_size = 0%') }
  else if (row.risk_state === 'Elevated') { parts.push('Elev'); tip.push('Risk: Elevated — proceed with caution') }
  return { compact: parts.join(' · '), tooltip: tip.join('\n') }
}

// Column header tooltip strings (extracted to keep StockScreener under 600 LOC)
export const COL_TOOLTIPS = {
  conviction: [
    'Score 0–100: where this stock ranks among peers in the same size tier (Mega, Large, Mid, Small).',
    '',
    '50 = median for its tier. 70+ = top 30% of peers. 30 or below = bottom 30%.',
    '',
    'Based on 11 technical signals: momentum, trend, volume, and risk. Higher = better overall technical picture relative to size-similar stocks.',
    '',
    'Percentile is within-tier only — do not compare Mega-cap scores to Small-cap scores directly.',
  ].join('\n'),
  quality: [
    'Composite quality letter from 6 signals: RS state, Momentum, Risk, Volume, Stage 2 (above rising 30W MA), and RS Percentile.',
    '',
    'A (score ≥5): strong positive alignment across signals',
    'B (score 1–4): mixed — some signals positive, others not',
    'C (score ≤0): predominantly negative signals',
    '',
    'Hover any grade cell to see the per-signal score breakdown.',
  ].join('\n'),
}

export function GateDot({ value }: { value: boolean | null }) {
  const color = value === true
    ? 'bg-teal'
    : value === false ? 'bg-signal-neg' : 'bg-paper-rule'
  return <span className={`w-1.5 h-1.5 rounded-full ${color} shrink-0`} />
}

export function GateDots({ row }: { row: StockRowWithSector }) {
  const vals = GATE_LEGEND.map(g => optBool(row, g.field))
  const passCount = vals.filter(v => v === true).length
  const tooltipText = GATE_LEGEND.map((g, i) =>
    `${g.key}=${g.label}: ${vals[i] === true ? '✓' : vals[i] === false ? '✗' : '?'} — ${g.desc}`
  ).join('\n')
  return (
    <span
      className="inline-flex items-center gap-0.5"
      title={tooltipText}
    >
      {vals.map((v, i) => <GateDot key={i} value={v} />)}
      <span className="ml-1 font-mono text-[10px] text-ink-tertiary tabular-nums">{passCount}/9</span>
    </span>
  )
}
