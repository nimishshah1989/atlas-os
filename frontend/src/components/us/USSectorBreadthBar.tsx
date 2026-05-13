import type { USSectorBreadthRow } from '@/lib/queries/us-stocks'

const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']

const RS_COLOR: Record<string, string> = {
  Leader:        '#22c55e',
  Strong:        '#1D9E75',
  Consolidating: '#0ea5e9',
  Emerging:      '#f59e0b',
  Average:       '#94a3b8',
  Weak:          '#f97316',
  Laggard:       '#ef4444',
}

const SECTOR_ORDER = [
  'Information Technology',
  'Health Care',
  'Financials',
  'Consumer Discretionary',
  'Communication Services',
  'Industrials',
  'Consumer Staples',
  'Energy',
  'Materials',
  'Real Estate',
  'Utilities',
]

const SECTOR_ABBREV: Record<string, string> = {
  'Information Technology':  'Tech',
  'Health Care':             'Health',
  'Financials':              'Fin',
  'Consumer Discretionary':  'Disc',
  'Communication Services':  'Comm',
  'Industrials':             'Ind',
  'Consumer Staples':        'Staples',
  'Energy':                  'Energy',
  'Materials':               'Matl',
  'Real Estate':             'R.Est',
  'Utilities':               'Util',
}

type Props = { sectorBreadth: USSectorBreadthRow[] }

export function USSectorBreadthBar({ sectorBreadth }: Props) {
  const bySection = new Map<string, Record<string, number>>()
  for (const row of sectorBreadth) {
    if (!bySection.has(row.gics_sector)) bySection.set(row.gics_sector, {})
    bySection.get(row.gics_sector)![row.rs_state] = row.cnt
  }

  const sectors = SECTOR_ORDER.filter(s => bySection.has(s))
  if (sectors.length === 0) return null

  return (
    <div className="border border-paper-rule rounded-sm p-4">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
        S&amp;P 500 — Sector RS Breadth
      </div>
      <div className="space-y-2">
        {sectors.map(sector => {
          const counts = bySection.get(sector)!
          const total = RS_ORDER.reduce((sum, s) => sum + (counts[s] ?? 0), 0)
          if (total === 0) return null
          const leaderPct = Math.round(((counts['Leader'] ?? 0) + (counts['Strong'] ?? 0)) / total * 100)
          return (
            <div key={sector} className="flex items-center gap-3">
              <span className="font-sans text-[11px] text-ink-secondary w-14 shrink-0 text-right">
                {SECTOR_ABBREV[sector] ?? sector}
              </span>
              <div className="flex-1 flex h-4 rounded-sm overflow-hidden gap-px bg-paper-rule">
                {RS_ORDER.map(state => {
                  const cnt = counts[state] ?? 0
                  if (cnt === 0) return null
                  const pct = (cnt / total) * 100
                  return (
                    <div
                      key={state}
                      title={`${state}: ${cnt}`}
                      style={{ width: `${pct}%`, background: RS_COLOR[state] }}
                    />
                  )
                })}
              </div>
              <span className="font-mono text-[10px] text-ink-tertiary w-8 text-right">
                {leaderPct}%
              </span>
            </div>
          )
        })}
      </div>
      <div className="flex items-center gap-4 mt-3 flex-wrap">
        {RS_ORDER.map(state => (
          <span key={state} className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary">
            <span className="inline-block w-2 h-2 rounded-sm" style={{ background: RS_COLOR[state] }} />
            {state}
          </span>
        ))}
      </div>
    </div>
  )
}
