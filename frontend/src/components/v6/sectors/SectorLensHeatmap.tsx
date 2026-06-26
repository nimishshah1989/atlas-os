// Sector-level 6-lens vector heatmap — shows each sector's average lens scores.
// Pure server component.

import { toNumber } from '@/lib/v6/decimal'

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

// postgres returns NUMERIC as string — coerce defensively so .toFixed works.
// toNumber() throws on genuinely non-numeric input (visible failure) but accepts
// the number|string union at runtime; null/undefined pass through as null.
const num = (v: number | string | null): number | null =>
  toNumber(v as string | null | undefined)

const LENS_LABELS: Record<string, string> = {
  technical: 'Tech',
  fundamental: 'Fund',
  valuation: 'Val',
  catalyst: 'Cat',
  flow: 'Flow',
  policy: 'Pol',
}

// Lens scores are 0–100 (not 1–10 deciles), so the perceptual decile ramp doesn't
// apply; we RAG-tint by score band instead — high → sig-pos, low → sig-neg, mid → warn.
// color-mix keeps the tints theme-aware against the panel surface.
function cellStyle(v: number | null): React.CSSProperties {
  if (v == null) return { color: 'var(--color-txt-3)' }
  const band =
    v >= 65 ? ['var(--color-sig-pos)', 30] :
    v >= 55 ? ['var(--color-sig-pos)', 15] :
    v >= 45 ? ['var(--color-sig-warn)', 15] :
    v >= 35 ? ['var(--color-sig-neg)', 15] :
              ['var(--color-sig-neg)', 30]
  return { background: `color-mix(in srgb, ${band[0]} ${band[1]}%, transparent)`, color: 'var(--color-txt-1)' }
}

export function SectorLensHeatmap({ vectors }: Props) {
  if (vectors.length === 0) return null

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-sans border-collapse">
        <thead>
          <tr className="border-b border-edge-rule">
            <th className="text-left px-3 py-2 font-num text-[9px] uppercase tracking-wider font-semibold text-txt-3">Sector</th>
            <th className="text-right px-3 py-2 font-num text-[9px] uppercase tracking-wider font-semibold text-txt-3">Composite</th>
            {LENS_KEYS.map(k => (
              <th key={k} className="text-center px-2 py-2 font-num text-[9px] uppercase tracking-wider font-semibold text-txt-3">{LENS_LABELS[k]}</th>
            ))}
            <th className="text-right px-3 py-2 font-num text-[9px] uppercase tracking-wider font-semibold text-txt-3">Stocks</th>
          </tr>
        </thead>
        <tbody>
          {vectors.map(row => (
            <tr key={row.sector} className="border-b border-edge-hair hover:bg-surface-raised/50 transition-colors">
              <td className="px-3 py-2 font-medium text-txt-1">
                <a href={`/sectors/${encodeURIComponent(row.sector)}`} className="text-brand hover:underline">
                  {row.sector}
                </a>
              </td>
              <td className="px-3 py-2 text-right font-num font-semibold tabular-nums text-txt-1">
                {num(row.composite)?.toFixed(1) ?? '—'}
              </td>
              {LENS_KEYS.map(k => {
                const v = num(row[k])
                return (
                  <td key={k} className="px-2 py-2 text-center font-num tabular-nums font-medium" style={cellStyle(v)}>
                    {v?.toFixed(0) ?? '—'}
                  </td>
                )
              })}
              <td className="px-3 py-2 text-right font-num tabular-nums text-txt-3">{row.stock_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
