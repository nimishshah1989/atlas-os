import type { StockRowWithSector } from '@/lib/queries/stocks'

type MaFilter = 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null

const RS_STATES = ['Leader', 'Strong', 'Emerging', 'Consolidating', 'Average', 'Weak', 'Laggard'] as const
const RS_COLORS: Record<string, string> = {
  Leader:        '#2F6B43',
  Strong:        '#4CAF78',
  Emerging:      '#d97706',
  Consolidating: '#1D9E75',
  Average:       '#94a3b8',
  Weak:          '#ef6644',
  Laggard:       '#B0492C',
}

function barColor(pct: number) {
  return pct >= 0.6 ? '#2F6B43' : pct >= 0.4 ? '#f59e0b' : '#ef4444'
}

function getBool(s: StockRowWithSector, key: string): boolean {
  return (s as unknown as Record<string, unknown>)[key] === true
}

function MaTile({
  label,
  count,
  total,
  filterKey,
  active,
  onClick,
}: {
  label: string
  count: number
  total: number
  filterKey: MaFilter
  active: boolean
  onClick: (k: MaFilter) => void
}) {
  const pct = total > 0 ? count / total : 0
  const color = barColor(pct)
  return (
    <button
      type="button"
      onClick={() => onClick(active ? null : filterKey)}
      className={`flex flex-col gap-1.5 px-4 py-2.5 border rounded-sm min-w-[160px] text-left transition-colors ${
        active
          ? 'border-teal bg-teal/5'
          : 'border-paper-rule bg-paper hover:bg-paper-rule/20'
      }`}
    >
      <div className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
        {label}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-lg font-semibold text-ink-primary tabular-nums">{count}</span>
        <span className="font-sans text-xs text-ink-tertiary">of {total}</span>
      </div>
      <div className="w-full h-1 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.round(pct * 100)}%`, background: color }} />
      </div>
      <div className="font-mono text-[10px] tabular-nums" style={{ color }}>
        {Math.round(pct * 100)}%{active ? ' · filter active' : ''}
      </div>
    </button>
  )
}

function CompositionBar({ label, arr }: { label: string; arr: StockRowWithSector[] }) {
  const n = arr.length
  if (n === 0) return null
  const counts = RS_STATES.map(s => ({ state: s, count: arr.filter(r => r.rs_state === s).length }))

  return (
    <div className="flex flex-col gap-1.5 min-w-[120px]">
      <div className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
        {label}
        <span className="font-normal normal-case tracking-normal ml-1 text-ink-tertiary/60">({n})</span>
      </div>
      <div
        className="flex h-3 rounded-sm overflow-hidden w-full"
        title={counts.map(r => `${r.state}: ${r.count} (${n > 0 ? Math.round((r.count / n) * 100) : 0}%)`).join(' · ')}
      >
        {counts.filter(r => r.count > 0).map(r => (
          <div
            key={r.state}
            className="h-full"
            style={{ width: `${(r.count / n) * 100}%`, background: RS_COLORS[r.state] }}
            title={`${r.state}: ${r.count} (${Math.round((r.count / n) * 100)}%)`}
          />
        ))}
      </div>
      <div className="space-y-0.5">
        {counts
          .filter(r => r.count > 0)
          .slice(0, 3)
          .map(r => (
            <div key={r.state} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary">
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: RS_COLORS[r.state] }} />
                {r.state}
              </span>
              <span className="font-mono text-[10px] tabular-nums text-ink-secondary">
                {Math.round((r.count / n) * 100)}%
              </span>
            </div>
          ))}
      </div>
    </div>
  )
}

export function StockBreadthPanel({
  stocks,
  activeMaFilter,
  onMaFilter,
}: {
  stocks: StockRowWithSector[]
  activeMaFilter: MaFilter
  onMaFilter: (f: MaFilter) => void
}) {
  const total = stocks.length
  const above30w  = stocks.filter(s => s.above_30w_ma === true).length
  const above50d  = stocks.filter(s => getBool(s, 'above_50d_ma')).length
  const above200d = stocks.filter(s => getBool(s, 'above_200d_ma')).length

  const n50  = stocks.filter(s => s.in_nifty_50)
  const n100 = stocks.filter(s => s.in_nifty_100)
  const n500 = stocks.filter(s => s.in_nifty_500)

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      {/* Band 1: MA metrics */}
      <div className="px-4 py-3 border-b border-paper-rule">
        <div className="flex items-center gap-3 mb-3">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Market Breadth — Moving Average Participation
          </div>
          {activeMaFilter && (
            <button
              type="button"
              onClick={() => onMaFilter(null)}
              className="font-sans text-[10px] text-teal hover:underline"
            >
              Clear filter ×
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          <MaTile label="Above 30-Week MA"  count={above30w}  total={total} filterKey="above_30w_ma"  active={activeMaFilter === 'above_30w_ma'}  onClick={onMaFilter} />
          <MaTile label="Above 50-Day EMA"  count={above50d}  total={total} filterKey="above_50d_ma"  active={activeMaFilter === 'above_50d_ma'}  onClick={onMaFilter} />
          <MaTile label="Above 200-Day EMA" count={above200d} total={total} filterKey="above_200d_ma" active={activeMaFilter === 'above_200d_ma'} onClick={onMaFilter} />
        </div>
      </div>

      {/* Band 2: Index composition */}
      <div className="px-4 py-3">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
          RS State Composition by Index
        </div>
        <div className="flex flex-wrap gap-6">
          <CompositionBar label="Nifty 50"  arr={n50} />
          <CompositionBar label="Nifty 100" arr={n100} />
          <CompositionBar label="Nifty 500" arr={n500} />
          <CompositionBar label="All"       arr={stocks} />
        </div>
        <div className="flex flex-wrap gap-3 mt-3 pt-2 border-t border-paper-rule/40">
          {RS_STATES.map(s => (
            <span key={s} className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary">
              <span className="w-2 h-2 rounded-full" style={{ background: RS_COLORS[s] }} />
              {s}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
