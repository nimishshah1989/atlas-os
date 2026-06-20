// Sector-level 6-lens vector heatmap — shows each sector's average lens scores.
// Pure server component.

type SectorVector = {
  sector: string
  technical: number | null
  fundamental: number | null
  valuation: number | null
  catalyst: number | null
  flow: number | null
  policy: number | null
  composite: number | null
  stock_count: number
}

type Props = {
  vectors: SectorVector[]
}

const LENS_KEYS = ['technical', 'fundamental', 'valuation', 'catalyst', 'flow', 'policy'] as const

const LENS_LABELS: Record<string, string> = {
  technical: 'Tech',
  fundamental: 'Fund',
  valuation: 'Val',
  catalyst: 'Cat',
  flow: 'Flow',
  policy: 'Pol',
}

function cellColor(v: number | null): string {
  if (v == null) return 'bg-paper-rule/10 text-ink-tertiary'
  if (v >= 65) return 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-300'
  if (v >= 55) return 'bg-emerald-50 text-emerald-800 dark:bg-emerald-900/15 dark:text-emerald-400'
  if (v >= 45) return 'bg-amber-50 text-amber-800 dark:bg-amber-900/15 dark:text-amber-400'
  if (v >= 35) return 'bg-orange-50 text-orange-800 dark:bg-orange-900/15 dark:text-orange-400'
  return 'bg-red-100 text-red-900 dark:bg-red-900/30 dark:text-red-300'
}

export function SectorLensHeatmap({ vectors }: Props) {
  if (vectors.length === 0) return null

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-sans border-collapse">
        <thead>
          <tr className="border-b border-paper-rule">
            <th className="text-left px-3 py-2 font-medium text-ink-tertiary">Sector</th>
            <th className="text-right px-3 py-2 font-medium text-ink-tertiary">Composite</th>
            {LENS_KEYS.map(k => (
              <th key={k} className="text-center px-2 py-2 font-medium text-ink-tertiary">{LENS_LABELS[k]}</th>
            ))}
            <th className="text-right px-3 py-2 font-medium text-ink-tertiary">Stocks</th>
          </tr>
        </thead>
        <tbody>
          {vectors.map(row => (
            <tr key={row.sector} className="border-b border-paper-rule/50 hover:bg-paper-soft/50 transition-colors">
              <td className="px-3 py-2 font-medium text-ink-primary">
                <a href={`/sectors/${encodeURIComponent(row.sector)}`} className="text-accent hover:underline">
                  {row.sector}
                </a>
              </td>
              <td className="px-3 py-2 text-right font-semibold tabular-nums text-ink-primary">
                {row.composite?.toFixed(1) ?? '—'}
              </td>
              {LENS_KEYS.map(k => {
                const v = row[k]
                return (
                  <td key={k} className={`px-2 py-2 text-center tabular-nums font-medium ${cellColor(v)}`}>
                    {v?.toFixed(0) ?? '—'}
                  </td>
                )
              })}
              <td className="px-3 py-2 text-right tabular-nums text-ink-tertiary">{row.stock_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
